"""Integrated LinkBox main-tab registration."""

TAB_TITLE = "📦 File Receiver (LinkBox)"


def register_tab(tab_widget, content_widget):
    """Register LinkBox content in the integrated PrintShopApp tabs."""
    return tab_widget.addTab(content_widget, TAB_TITLE)
