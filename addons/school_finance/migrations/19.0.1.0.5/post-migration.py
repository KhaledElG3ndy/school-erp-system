def migrate(cr, version):
    cr.execute("DROP TABLE IF EXISTS school_finance_dashboard_period")
    cr.execute("DROP TABLE IF EXISTS school_finance_dashboard")
