import QtQuick

// Progressione del primato di una gara: un punto per ogni miglioramento (dal primo risultato all'ultimo primato), `y` in 0-1 con il miglioramento
// sempre verso l'alto. Disegna solo ciò che arriva da Python (`points`: label, y, display, tip).
Item {
    id: root
    property var points: []
    property int hoverIdx: -1
    property real reveal: 1
    readonly property int n: points.length
    readonly property real mL: 10
    readonly property real mR: 10
    readonly property real mT: 14
    readonly property real mB: 22
    implicitHeight: 96

    function px(i) { return n > 1 ? mL + (width - mL - mR) * i / (n - 1) : mL + (width - mL - mR) / 2 }
    function py(y) { return mT + (height - mT - mB) * (1 - y) }
    function rgba(hex, a) { var c = Qt.color(hex); return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }

    onPointsChanged: { if (Theme.animScale > 0 && n > 1) { reveal = 0; draw.restart() } cv.requestPaint() }
    onHoverIdxChanged: cv.requestPaint()
    onRevealChanged: cv.requestPaint()
    onWidthChanged: cv.requestPaint()
    onHeightChanged: cv.requestPaint()
    NumberAnimation { id: draw; target: root; property: "reveal"; from: 0; to: 1; duration: 600 * Theme.animScale; easing.type: Easing.OutCubic }

    Canvas {
        id: cv
        anchors.fill: parent
        renderTarget: Canvas.Image   // il default (FBO) non esiste nel backend software
        renderStrategy: Canvas.Immediate
        Component.onCompleted: requestPaint()
        onPaint: {
            var ctx = getContext("2d"); ctx.reset()
            ctx.strokeStyle = Theme.border; ctx.lineWidth = 1
            ctx.beginPath(); ctx.moveTo(root.mL, height - root.mB + 0.5); ctx.lineTo(width - root.mR, height - root.mB + 0.5); ctx.stroke()
            if (root.n < 1) return
            ctx.save(); ctx.beginPath(); ctx.rect(0, 0, root.mL + (width - root.mL) * root.reveal, height); ctx.clip()
            if (root.n > 1) {
                var g = ctx.createLinearGradient(0, root.mT, 0, height - root.mB)
                g.addColorStop(0, root.rgba(Theme.warn, 0.22)); g.addColorStop(1, root.rgba(Theme.warn, 0))
                ctx.beginPath(); ctx.moveTo(root.px(0), height - root.mB)
                for (var i = 0; i < root.n; i++) ctx.lineTo(root.px(i), root.py(root.points[i].y))
                ctx.lineTo(root.px(root.n - 1), height - root.mB); ctx.closePath(); ctx.fillStyle = g; ctx.fill()
                ctx.strokeStyle = Theme.warn; ctx.lineWidth = 2.2; ctx.lineJoin = "round"; ctx.lineCap = "round"
                ctx.beginPath()
                for (var j = 0; j < root.n; j++) { if (j === 0) ctx.moveTo(root.px(j), root.py(root.points[j].y)); else ctx.lineTo(root.px(j), root.py(root.points[j].y)) }
                ctx.stroke()
            }
            for (var k = 0; k < root.n; k++) {
                var x = root.px(k), yy = root.py(root.points[k].y), last = k === root.n - 1
                ctx.fillStyle = last ? Theme.warn : Theme.accent; ctx.strokeStyle = Theme.surface; ctx.lineWidth = 2
                ctx.beginPath(); ctx.arc(x, yy, (k === root.hoverIdx || last) ? 5.5 : 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
            }
            ctx.restore()
            ctx.fillStyle = Theme.textFaint; ctx.textBaseline = "top"; ctx.font = "10px sans-serif"
            ctx.textAlign = "left"; ctx.fillText(root.points[0].label, root.mL, height - root.mB + 6)
            if (root.n > 1) { ctx.textAlign = "right"; ctx.fillText(root.points[root.n - 1].label, width - root.mR, height - root.mB + 6) }
        }
    }
    MouseArea {
        id: ma; anchors.fill: parent; hoverEnabled: true; enabled: root.n > 0
        onPositionChanged: (m) => {
            var frac = (m.x - root.mL) / Math.max(1, width - root.mL - root.mR)
            root.hoverIdx = root.n > 1 ? Math.max(0, Math.min(root.n - 1, Math.round(frac * (root.n - 1)))) : 0
        }
        onExited: root.hoverIdx = -1
    }
    Tip { visible: ma.containsMouse && root.hoverIdx >= 0 && root.hoverIdx < root.n; text: root.hoverIdx >= 0 && root.hoverIdx < root.n ? root.points[root.hoverIdx].tip : ""
          x: ma.mouseX + 12; y: ma.mouseY + 16 }
}
