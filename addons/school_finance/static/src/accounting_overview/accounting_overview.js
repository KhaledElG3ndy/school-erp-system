/** @odoo-module **/

import { loadBundle } from "@web/core/assets";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { formatInteger, formatMonetary } from "@web/views/fields/formatters";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

import {
    Component,
    onWillStart,
    onWillUnmount,
    useEffect,
    useRef,
    useState,
} from "@odoo/owl";

export class SchoolAccountingOverview extends Component {
    static template = "school_finance.SchoolAccountingOverview";
    static props = { ...standardActionServiceProps };

    setup() {
        this.actionService = useService("action");
        this.notification = useService("notification");
        this.orm = useService("orm");
        this.movementCanvas = useRef("movementCanvas");
        this.liquidityCanvas = useRef("liquidityCanvas");
        this.charts = [];
        this.state = useState({
            loading: true,
            data: null,
            filters: {
                date_from: "",
                date_to: "",
                company_id: false,
                analytic_account_id: false,
            },
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.loadOverview();
        });
        useEffect(
            () => {
                this.renderCharts();
                return () => this.destroyCharts();
            },
            () => [this.state.data]
        );
        onWillUnmount(() => this.destroyCharts());
    }

    get direction() {
        return this.state.data?.direction || "ltr";
    }

    get quickLinks() {
        return [
            { key: "customer_invoices", label: _t("Customer Invoices") },
            { key: "payments", label: _t("Payments") },
            { key: "vendor_bills", label: _t("Vendor Bills") },
            { key: "bank_journals", label: _t("Bank Journals") },
            { key: "cash_journals", label: _t("Cash Journals") },
            { key: "journal_entries", label: _t("Journal Entries") },
            { key: "budgets", label: _t("Budgets") },
            { key: "assets", label: _t("Assets") },
        ];
    }

    async loadOverview(values = this.state.filters) {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "account.move.line",
                "get_school_accounting_overview",
                [values]
            );
            this.state.data = data;
            Object.assign(this.state.filters, data.filters);
        } catch (error) {
            this.notification.add(
                error?.data?.message || _t("Unable to load the accounting overview."),
                { type: "danger" }
            );
        } finally {
            this.state.loading = false;
        }
    }

    async applyFilters() {
        await this.loadOverview();
    }

    async resetFilters() {
        this.state.filters.date_from = "";
        this.state.filters.date_to = "";
        this.state.filters.company_id = false;
        this.state.filters.analytic_account_id = false;
        await this.loadOverview({});
    }

    onDateFromChange(event) {
        this.state.filters.date_from = event.target.value;
    }

    onDateToChange(event) {
        this.state.filters.date_to = event.target.value;
    }

    async onCompanyChange(event) {
        this.state.filters.company_id = Number(event.target.value);
        this.state.filters.analytic_account_id = false;
        await this.loadOverview();
    }

    onAnalyticAccountChange(event) {
        this.state.filters.analytic_account_id = event.target.value
            ? Number(event.target.value)
            : false;
    }

    formatMoney(value) {
        const formatted = formatMonetary(value || 0, {
            currencyId: this.state.data.currency_id,
        });
        if (
            this.direction === "rtl" &&
            this.state.data.currency_code === "SAR"
        ) {
            return formatted.replace(/\b(?:SAR|SR)\b/g, "ر.س");
        }
        return formatted;
    }

    formatCount(value) {
        return formatInteger(value || 0);
    }

    async openTarget(target) {
        const action = await this.orm.call(
            "account.move.line",
            "open_school_accounting_overview_target",
            [target, this.state.filters]
        );
        await this.actionService.doAction(action);
    }

    destroyCharts() {
        for (const chart of this.charts) {
            chart.destroy();
        }
        this.charts = [];
    }

    renderCharts() {
        this.destroyCharts();
        if (
            !this.state.data ||
            !this.movementCanvas.el ||
            !this.liquidityCanvas.el
        ) {
            return;
        }

        const isRTL = this.direction === "rtl";
        const movement = this.state.data.charts.movement;
        const commonLegend = {
            position: "bottom",
            rtl: isRTL,
            textDirection: isRTL ? "rtl" : "ltr",
            labels: {
                boxWidth: 10,
                boxHeight: 10,
                usePointStyle: true,
                padding: 18,
                color: "#0b1f45",
            },
        };
        const movementChart = new Chart(this.movementCanvas.el, {
            type: "bar",
            data: {
                labels: movement.map((item) => item.key),
                datasets: [
                    {
                        label: _t("Revenue"),
                        data: movement.map((item) => item.revenue),
                        backgroundColor: "#714b67",
                        borderColor: "#714b67",
                        borderRadius: 5,
                        borderSkipped: false,
                        maxBarThickness: 34,
                    },
                    {
                        label: _t("Expenses"),
                        data: movement.map((item) => item.expense),
                        backgroundColor: "#159fbc",
                        borderColor: "#159fbc",
                        borderRadius: 5,
                        borderSkipped: false,
                        maxBarThickness: 34,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                aspectRatio: 2.35,
                interaction: {
                    intersect: false,
                    mode: "index",
                },
                plugins: {
                    legend: commonLegend,
                    tooltip: {
                        rtl: isRTL,
                        textDirection: isRTL ? "rtl" : "ltr",
                        callbacks: {
                            label: (context) =>
                                `${context.dataset.label}: ${this.formatMoney(
                                    context.parsed.y
                                )}`,
                        },
                    },
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { color: "#0b1f45" },
                    },
                    y: {
                        beginAtZero: true,
                        border: { display: false },
                        grid: { color: "rgba(11, 31, 69, 0.08)" },
                        ticks: {
                            color: "#0b1f45",
                            callback: (value) =>
                                formatMonetary(value, {
                                    currencyId: this.state.data.currency_id,
                                    noSymbol: true,
                                    humanReadable: true,
                                }),
                        },
                    },
                },
            },
        });

        const liquidity = this.state.data.charts.liquidity;
        const liquidityValues = [liquidity.bank, liquidity.cash];
        const liquidityChart = new Chart(this.liquidityCanvas.el, {
            type: "doughnut",
            data: {
                labels: [_t("Bank"), _t("Cash")],
                datasets: [
                    {
                        data: liquidityValues.map((value) => Math.abs(value)),
                        backgroundColor: ["#714b67", "#008a9a"],
                        borderColor: ["#714b67", "#008a9a"],
                        borderWidth: 1,
                        hoverOffset: 5,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                aspectRatio: 1.65,
                cutout: "68%",
                plugins: {
                    legend: commonLegend,
                    tooltip: {
                        rtl: isRTL,
                        textDirection: isRTL ? "rtl" : "ltr",
                        callbacks: {
                            label: (context) =>
                                `${context.label}: ${this.formatMoney(
                                    liquidityValues[context.dataIndex]
                                )}`,
                        },
                    },
                },
            },
        });
        this.charts.push(movementChart, liquidityChart);
    }
}

registry
    .category("actions")
    .add("school_finance.accounting_overview", SchoolAccountingOverview);
