{
    "name": "Asset Request",
    "summary": "Asset Request - Module Rentals",
    "version": "1.0",
    "license": "OEEL-1",
    "author": "Rentals",
    "depends": [
        "base","fleet","mail","account"
    ],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "data/sequence_data.xml",
        "data/cron_data.xml",
        "views/asset_request_views.xml",
        "views/asset_leasing_amortization_views.xml",
        "views/asset_request_delegate_views.xml",
        "views/asset_approval_config_views.xml",
        "views/asset_request_menus.xml",
    ],
    'installable': True,
    'application': True,
}