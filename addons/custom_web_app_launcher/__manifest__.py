{
    "name": "Custom Web App Launcher",
    "version": "19.0.1.0.1",
    "category": "Hidden",
    "summary": "Open a full app launcher from the backend Apps navbar icon",
    "author": "TelNova",
    "depends": ["web"],
    "data": [
        "views/app_launcher_action.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "custom_web_app_launcher/static/src/app_launcher/**/*.js",
            "custom_web_app_launcher/static/src/app_launcher/**/*.xml",
            "custom_web_app_launcher/static/src/app_launcher/**/*.scss",
        ],
    },
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
