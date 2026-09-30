/**
 * RevenueCat bootstrap for the React Native app.
 *
 *   import { initPurchases } from "./lib/revenuecat";
 *   useEffect(() => {
 *     let cleanup;
 *     initPurchases({ onChange: reloadMe }).then((fn) => { cleanup = fn; });
 *     return () => cleanup && cleanup();
 *   }, []);
 *
 * - Configures Purchases with the platform key.
 * - Hands Purchases.getAppUserID() to the API client, so every request
 *   carries `Authorization: Bearer <appUserID>` — the same id RevenueCat
 *   sends in webhooks, which is how the backend knows who is Pro.
 * - Calls onChange() whenever entitlements change (purchase, restore,
 *   renewal, expiry) so the app re-fetches /me and the Pro screens.
 *
 * Keys: public SDK keys are safe to ship. `test_…` keys only work with
 * RevenueCat's Test Store; use appl_… (iOS) and goog_… (Android) for
 * TestFlight / Play testing and release.
 */
import { Platform } from "react-native";
import Purchases, { LOG_LEVEL } from "react-native-purchases";

import { setAppUserId } from "./apiClient";

const env = (typeof process !== "undefined" && process.env) || {};
const KEYS = {
  ios: env.EXPO_PUBLIC_RC_IOS_KEY || "test_BXDlovvspMnZNnEoOzpphXPOKnB",
  android: env.EXPO_PUBLIC_RC_ANDROID_KEY || "test_BXDlovvspMnZNnEoOzpphXPOKnB",
};

let configured = false;

export async function initPurchases({ onChange } = {}) {
  if (!configured) {
    if (__DEV__) Purchases.setLogLevel(LOG_LEVEL.VERBOSE);
    const apiKey = Platform.OS === "ios" ? KEYS.ios : KEYS.android;
    Purchases.configure({ apiKey });
    configured = true;
  }
  setAppUserId(await Purchases.getAppUserID());

  const listener = async () => {
    // The backend also learns via the webhook; /me refreshes from RevenueCat.
    setAppUserId(await Purchases.getAppUserID());
    if (onChange) onChange();
  };
  Purchases.addCustomerInfoUpdateListener(listener);
  return () => Purchases.removeCustomerInfoUpdateListener(listener);
}

/** Restore purchases (App Store requires a visible "Restore" button). */
export async function restorePurchases() {
  await Purchases.restorePurchases();
  setAppUserId(await Purchases.getAppUserID());
}
