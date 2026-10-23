"""Integrated LinkShare main-tab registration."""

TAB_TITLE = "🌐 Wi-Fi Pass Manager (LinkShare)"


def register_tab(tab_widget, content_widget):
    """Register LinkShare content in the integrated PrintShopApp tabs."""
    return tab_widget.addTab(content_widget, TAB_TITLE)
