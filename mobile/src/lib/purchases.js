/**
 * Identity + subscriptions.
 *
 * Web (the PWA at app.turnaroundiq.co.uk): email-code sign-in; the session
 * token is the API bearer. Paying opens RevenueCat's hosted Web Purchase
 * Link (Stripe) for the signed-in account; RevenueCat's webhook tells the
 * API, and /me reports Pro. Managing opens the RevenueCat/Stripe portal.
 *
 * Native (Capacitor iOS/Android, later): RevenueCat SDK + store purchases.
 */
import { Capacitor } from "@capacitor/core";

import { api, setUserId } from "./api";

const ENTITLEMENT = import.meta.env.VITE_RC_ENTITLEMENT || "pro";
const SESSION_KEY = "tiq_session";
export const isNative = Capacitor.isNativePlatform();
export const purchasesAvailable = true;

let Purchases = null;
async function sdk() {
  if (!isNative) return null;
  if (!Purchases) Purchases = (await import("@revenuecat/purchases-capacitor")).Purchases;
  return Purchases;
}

function storage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

// ---- web session ----------------------------------------------------------
export function getSession() {
  return storage()?.getItem(SESSION_KEY) || null;
}
function saveSession(token) {
  const s = storage();
  if (!s) return;
  if (token) s.setItem(SESSION_KEY, token);
  else s.removeItem(SESSION_KEY);
}
export async function startSignIn(email) {
  await api.authStart(email);
}
export async function finishSignIn(email, code) {
  const { token } = await api.authVerify(email, code);
  saveSession(token);
  setUserId(token);
  return token;
}
export async function signOut() {
  try {
    await api.authLogout();
  } catch {
    // session may already be gone
  }
  saveSession(null);
  setUserId(null);
}
export function clearSession() {
  saveSession(null);
  setUserId(null);
}

// ---- boot -------------------------------------------------------------------
let ready = null;
/** Resolves with the bearer identity (null on web until signed in). */
export function initPurchases() {
  if (ready) return ready;
  ready = (async () => {
    const P = await sdk();
    if (!P) {
      const token = getSession() || import.meta.env.VITE_DEV_USER_ID || null;
      setUserId(token);
      return token;
    }
    const apiKey = Capacitor.getPlatform() === "ios"
      ? import.meta.env.VITE_RC_IOS_KEY
      : import.meta.env.VITE_RC_ANDROID_KEY;
    await P.configure({ apiKey });
    const { appUserID } = await P.getAppUserID();
    setUserId(appUserID);
    return appUserID;
  })();
  return ready;
}

/** Re-check entitlement when RevenueCat (native) or the user returning to the tab (web) says so. */
export async function onCustomerInfoChange(onChange) {
  const P = await sdk();
  if (!P) {
    const handler = () => document.visibilityState === "visible" && onChange();
    document.addEventListener("visibilitychange", handler);
    return () => document.removeEventListener("visibilitychange", handler);
  }
  const id = await P.addCustomerInfoUpdateListener((info) => {
    onChange(Boolean(info?.entitlements?.active?.[ENTITLEMENT]));
  });
  return () => P.removeCustomerInfoUpdateListener({ listenerToRemove: id });
}

// ---- buying -----------------------------------------------------------------
export async function getPackages() {
  const P = await sdk();
  if (!P) return [];
  const offerings = await P.getOfferings();
  return offerings?.current?.availablePackages || [];
}

export async function purchase(aPackage) {
  const P = await sdk();
  if (!P) return false;
  try {
    const { customerInfo } = await P.purchasePackage({ aPackage });
    return Boolean(customerInfo?.entitlements?.active?.[ENTITLEMENT]);
  } catch (e) {
    if (e?.userCancelled || /cancel/i.test(e?.message || "")) return false;
    throw e;
  }
}

/** Web: go to RevenueCat's hosted checkout for this account. */
export function openWebCheckout(purchaseUrl) {
  if (purchaseUrl) window.location.href = purchaseUrl;
}

export async function restore() {
  const P = await sdk();
  if (!P) return false; // web: signing in with the same email restores
  const { customerInfo } = await P.restorePurchases();
  return Boolean(customerInfo?.entitlements?.active?.[ENTITLEMENT]);
}

export async function manageSubscription(managementUrl) {
  const P = await sdk();
  if (!P) {
    if (managementUrl) window.open(managementUrl, "_blank");
    return;
  }
  const { customerInfo } = await P.getCustomerInfo();
  if (customerInfo?.managementURL) {
    const { Browser } = await import("@capacitor/browser");
    await Browser.open({ url: customerInfo.managementURL });
  }
}
