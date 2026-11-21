class SingleLineFitCheckBox(QCheckBox):
    """한 줄에 모두 표시하되 가용 폭을 넘으면 글꼴 크기를 자동으로 축소하는 체크박스."""

    def __init__(
        self,
        text: str = "",
        base_pt: float = 10.0,
        min_pt: float = 7.5,
        indicator_reserve_px: int = 22,
        h_pad: int = 8,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._full_text = text
        self._base_pt = base_pt
        self._min_pt = min_pt
        self._indicator_reserve_px = indicator_reserve_px
        self._h_pad = h_pad
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setText(text)

    def fullText(self) -> str:
        return self._full_text

    def setText(self, text: str) -> None:  # type: ignore[override]
        self._full_text = text or ""
        super().setToolTip(self._full_text)
        self._refit_font()
        self.updateGeometry()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refit_font()

    def _calc_fitted_font_and_width(self, available_width: int) -> tuple[Any, int]:
        font = self.font()
        clean_text = self._full_text or ""
        if not clean_text:
            font.setPointSizeF(self._base_pt)
            return font, self._indicator_reserve_px + self._h_pad

        text_budget = max(12, available_width - self._indicator_reserve_px - self._h_pad)
        chosen_pt = self._min_pt
        pt = self._base_pt
        while pt >= self._min_pt:
            font.setPointSizeF(pt)
            fm = QFontMetrics(font)
            if fm.horizontalAdvance(clean_text) <= text_budget:
                chosen_pt = pt
                break
            pt = round(pt - 0.5, 2)

        font.setPointSizeF(chosen_pt)
        fm = QFontMetrics(font)
        desired_w = fm.horizontalAdvance(clean_text) + self._indicator_reserve_px + self._h_pad
        return font, desired_w

    def _refit_font(self) -> None:
        avail = self.width() if self.width() > 0 else self.maximumWidth()
        if avail <= 0:
            avail = 10_000
        font, _ = self._calc_fitted_font_and_width(avail)
        self.setFont(font)
        super().setText(self._full_text)

    def sizeHint(self):
        hint = super().sizeHint()
        _, desired_w = self._calc_fitted_font_and_width(10_000)
        hint.setWidth(desired_w)
        return hint

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        font = self.font()
        font.setPointSizeF(self._min_pt)
        fm = QFontMetrics(font)
        min_text_w = fm.horizontalAdvance(self._full_text or "")
        hint.setWidth(min_text_w + self._indicator_reserve_px + self._h_pad)
        return hint