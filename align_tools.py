from PyQt5.QtCore import QRectF


def _bboxes(items):
    from canvas import ShapeItem
    return [(item, item.sceneBoundingRect()) for item in items if isinstance(item, ShapeItem)]


def align_left(canvas):
    pairs = _bboxes(canvas.scene().selectedItems())
    if len(pairs) < 2:
        return
    target = min(r.left() for _, r in pairs)
    for item, r in pairs:
        item.moveBy(target - r.left(), 0)


def align_right(canvas):
    pairs = _bboxes(canvas.scene().selectedItems())
    if len(pairs) < 2:
        return
    target = max(r.right() for _, r in pairs)
    for item, r in pairs:
        item.moveBy(target - r.right(), 0)


def align_top(canvas):
    pairs = _bboxes(canvas.scene().selectedItems())
    if len(pairs) < 2:
        return
    target = min(r.top() for _, r in pairs)
    for item, r in pairs:
        item.moveBy(0, target - r.top())


def align_bottom(canvas):
    pairs = _bboxes(canvas.scene().selectedItems())
    if len(pairs) < 2:
        return
    target = max(r.bottom() for _, r in pairs)
    for item, r in pairs:
        item.moveBy(0, target - r.bottom())


def align_center_h(canvas):
    pairs = _bboxes(canvas.scene().selectedItems())
    if len(pairs) < 2:
        return
    cx = sum(r.center().x() for _, r in pairs) / len(pairs)
    for item, r in pairs:
        item.moveBy(cx - r.center().x(), 0)


def align_center_v(canvas):
    pairs = _bboxes(canvas.scene().selectedItems())
    if len(pairs) < 2:
        return
    cy = sum(r.center().y() for _, r in pairs) / len(pairs)
    for item, r in pairs:
        item.moveBy(0, cy - r.center().y())


def distribute_h(canvas):
    pairs = _bboxes(canvas.scene().selectedItems())
    if len(pairs) < 3:
        return
    pairs.sort(key=lambda p: p[1].left())
    total_gap = pairs[-1][1].left() - pairs[0][1].right()
    inner_widths = sum(r.width() for _, r in pairs[1:-1])
    spacing = (total_gap - inner_widths) / (len(pairs) - 1)
    x = pairs[0][1].right() + spacing
    for item, r in pairs[1:-1]:
        item.moveBy(x - r.left(), 0)
        x += r.width() + spacing


def distribute_v(canvas):
    pairs = _bboxes(canvas.scene().selectedItems())
    if len(pairs) < 3:
        return
    pairs.sort(key=lambda p: p[1].top())
    total_gap = pairs[-1][1].top() - pairs[0][1].bottom()
    inner_heights = sum(r.height() for _, r in pairs[1:-1])
    spacing = (total_gap - inner_heights) / (len(pairs) - 1)
    y = pairs[0][1].bottom() + spacing
    for item, r in pairs[1:-1]:
        item.moveBy(0, y - r.top())
        y += r.height() + spacing
