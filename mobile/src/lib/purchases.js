/**
 * RevenueCat via Capacitor (App Store / Google Play in-app purchases).
 *
 * In a browser (npm run dev) there is no store: purchases are disabled and
 * VITE_DEV_USER_ID (a sandbox appUserID) is used so the API can be tested.
 */
import { Capacitor } from "@capacitor/core";

import { setUserId } from "./api";

const ENTITLEMENT = import.meta.env.VITE_RC_ENTITLEMENT || "pro";
const isNative = Capacitor.isNativePlatform();
let Purchases = null;
let ready = null;

async function sdk() {
  if (!isNative) return null;
  if (!Purchases) Purchases = (await import("@revenuecat/purchases-capacitor")).Purchases;
  return Purchases;
}

/** Configure once; resolves with the app user id (or null in a browser without a dev id). */
export function initPurchases() {
  if (ready) return ready;
  ready = (async () => {
    const P = await sdk();
    if (!P) {
      const dev = import.meta.env.VITE_DEV_USER_ID || null;
      setUserId(dev);
      return dev;
    }
    const apiKey =
      Capacitor.getPlatform() === "ios"
        ? import.meta.env.VITE_RC_IOS_KEY
        : import.meta.env.VITE_RC_ANDROID_KEY;
    await P.configure({ apiKey });
    const { appUserID } = await P.getAppUserID();
    setUserId(appUserID);
    return appUserID;
  })();
  return ready;
}

/** Calls onChange(isPro) whenever RevenueCat reports new customer info. */
export async function onCustomerInfoChange(onChange) {
  const P = await sdk();
  if (!P) return () => {};
  const id = await P.addCustomerInfoUpdateListener((info) => {
    onChange(Boolean(info?.entitlements?.active?.[ENTITLEMENT]));
  });
  return () => P.removeCustomerInfoUpdateListener({ listenerToRemove: id });
}

/** Packages of the current offering, for the paywall. */
export async function getPackages() {
  const P = await sdk();
  if (!P) return [];
  const offerings = await P.getOfferings();
  return offerings?.current?.availablePackages || [];
}

/** Returns true if the purchase completed, false if the user cancelled. */
export async function purchase(aPackage) {
  const P = await sdk();
  if (!P) throw new Error("Purchases are only available in the iOS / Android app.");
  try {
    const { customerInfo } = await P.purchasePackage({ aPackage });
    return Boolean(customerInfo?.entitlements?.active?.[ENTITLEMENT]);
  } catch (e) {
    if (e?.userCancelled || e?.code === "1" || /cancel/i.test(e?.message || "")) return false;
    throw e;
  }
}

export async function restore() {
  const P = await sdk();
  if (!P) return false;
  const { customerInfo } = await P.restorePurchases();
  return Boolean(customerInfo?.entitlements?.active?.[ENTITLEMENT]);
}

/** Opens the App Store / Play subscription management page. */
export async function manageSubscription() {
  const P = await sdk();
  if (!P) return;
  const { customerInfo } = await P.getCustomerInfo();
  if (customerInfo?.managementURL) {
    const { Browser } = await import("@capacitor/browser");
    await Browser.open({ url: customerInfo.managementURL });
  }
}

export const purchasesAvailable = isNative;
