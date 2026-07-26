import { Component, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { computeAppsAndMenuItems } from "@web/webclient/menus/menu_helpers";

export class CustomWebAppLauncher extends Component {
    static template = "custom_web_app_launcher.AppLauncher";
    static props = {
        ...standardActionServiceProps,
        action: { type: Object, optional: true },
        close: { type: Function, optional: true },
    };

    setup() {
        this.menuService = useService("menu");

        onMounted(() => {
            document.querySelector(".o_web_client")?.classList.add("o_custom_app_launcher_open");
        });
        onWillUnmount(() => {
            document.querySelector(".o_web_client")?.classList.remove("o_custom_app_launcher_open");
        });
    }

    get apps() {
        return computeAppsAndMenuItems(this.menuService.getMenuAsTree("root")).apps;
    }

    async openApp(app) {
        this.props.close?.();
        await this.menuService.selectMenu(app.id);
    }

    goBack() {
        this.props.close?.();
    }
}

registry.category("actions").add("custom_web_app_launcher.app_launcher", CustomWebAppLauncher);
