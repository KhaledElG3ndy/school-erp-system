import { browser } from "@web/core/browser/browser";
import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { NavBar } from "@web/webclient/navbar/navbar";
import { CustomWebAppLauncher } from "./app_launcher";

const launcherRegistryKey = "custom_web_app_launcher.AppLauncherOverlay";
const mainComponentsRegistry = registry.category("main_components");

patch(NavBar.prototype, {
    /**
     * The stock Odoo 19 community navbar opens a compact dropdown from the
     * desktop Apps icon. Route that icon to a full client-action launcher
     * instead, while keeping Odoo's menu service as the source of app data.
     */
    openCustomAppLauncher() {
        this._closeAppMenuSidebar();
        const previousUrl = browser.location.href;

        if (mainComponentsRegistry.contains(launcherRegistryKey)) {
            mainComponentsRegistry.remove(launcherRegistryKey);
        }

        const close = () => {
            if (mainComponentsRegistry.contains(launcherRegistryKey)) {
                mainComponentsRegistry.remove(launcherRegistryKey);
            }
            browser.history.replaceState(browser.history.state, "", previousUrl);
        };

        mainComponentsRegistry.add(launcherRegistryKey, {
            Component: CustomWebAppLauncher,
            props: { close },
        });

        browser.history.replaceState(
            browser.history.state,
            "",
            `${browser.location.origin}/odoo${browser.location.search}`
        );
    },
});
