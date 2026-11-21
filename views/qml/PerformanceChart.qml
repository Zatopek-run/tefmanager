import QtQuick

// Ultime gare individuali: posizione in 0-100 (100 = vittoria, 0 = ultimo o ritirato), confrontabile tra discipline; marcatori per vittoria, primato, ritiro.
Item {
    id: root
    property var points: []
    property string emptyText: ""
    property int hoverIdx: -1
    property real reveal: 1
    readonly property int n: points.length
    readonly property real mL: 30
    readonly property real mR: 14
    readonly property real mT: 12
    readonly property real mB: 26
    implicitHeight: 170

    function px(i) { return n > 1 ? mL + (width - mL - mR) * i / (n - 1) : mL + (width - mL - mR) / 2 }
    function py(v) { return mT + (height - mT - mB) * (1 - v / 100) }
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
        renderTarget: Canvas.Image
        renderStrategy: Canvas.Immediate
        Component.onCompleted: requestPaint()
        onPaint: {
            var ctx = getContext("2d"); ctx.reset()
            ctx.font = "11px sans-serif"; ctx.textAlign = "right"; ctx.textBaseline = "middle"
            var steps = [0, 50, 100]
            for (var s = 0; s < steps.length; s++) {
                var y = root.py(steps[s])
                ctx.strokeStyle = Theme.border; ctx.lineWidth = 1; ctx.setLineDash(steps[s] === 50 ? [2, 4] : [])
                ctx.beginPath(); ctx.moveTo(root.mL, y + 0.5); ctx.lineTo(width - root.mR, y + 0.5); ctx.stroke()
                ctx.fillStyle = Theme.textFaint; ctx.fillText(steps[s] === 100 ? "1°" : steps[s] === 0 ? "ult." : "", root.mL - 6, y)
            }
            ctx.setLineDash([])
            if (root.n < 1) return
            ctx.save(); ctx.beginPath(); ctx.rect(0, 0, root.mL + (width - root.mL) * root.reveal, height); ctx.clip()
            if (root.n > 1) {
                var g = ctx.createLinearGradient(0, root.mT, 0, height - root.mB)
                g.addColorStop(0, root.rgba(Theme.accent, 0.25)); g.addColorStop(1, root.rgba(Theme.accent, 0))
                ctx.beginPath(); ctx.moveTo(root.px(0), height - root.mB)
                for (var i = 0; i < root.n; i++) ctx.lineTo(root.px(i), root.py(root.points[i].percentile))
                ctx.lineTo(root.px(root.n - 1), height - root.mB); ctx.closePath(); ctx.fillStyle = g; ctx.fill()
                ctx.strokeStyle = Theme.accent; ctx.lineWidth = 2.4; ctx.lineJoin = "round"; ctx.lineCap = "round"
                ctx.beginPath()
                for (var j = 0; j < root.n; j++) { if (j === 0) ctx.moveTo(root.px(j), root.py(root.points[j].percentile)); else ctx.lineTo(root.px(j), root.py(root.points[j].percentile)) }
                ctx.stroke()
            }
            for (var k = 0; k < root.n; k++) {
                var p = root.points[k], x = root.px(k), yy = root.py(p.percentile)
                var big = k === root.hoverIdx
                if (p.out) {   // ritirato: croce rossa
                    ctx.strokeStyle = Theme.bad; ctx.lineWidth = 2.4
                    ctx.beginPath(); ctx.moveTo(x - 5, yy - 5); ctx.lineTo(x + 5, yy + 5); ctx.moveTo(x + 5, yy - 5); ctx.lineTo(x - 5, yy + 5); ctx.stroke()
                } else if (p.pb) {   // primato personale: rombo oro
                    ctx.fillStyle = Theme.warn; ctx.strokeStyle = Theme.surface; ctx.lineWidth = 2
                    ctx.beginPath(); ctx.moveTo(x, yy - 7); ctx.lineTo(x + 7, yy); ctx.lineTo(x, yy + 7); ctx.lineTo(x - 7, yy); ctx.closePath(); ctx.fill(); ctx.stroke()
                } else {
                    ctx.fillStyle = p.place === 1 ? Theme.good : Theme.accent; ctx.strokeStyle = Theme.surface; ctx.lineWidth = 2
                    ctx.beginPath(); ctx.arc(x, yy, big ? 6 : 4.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
                }
            }
            ctx.restore()
            ctx.fillStyle = Theme.textFaint; ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.font = "10px sans-serif"
            for (var m = 0; m < root.n; m += (root.n > 6 ? 2 : 1)) ctx.fillText(root.points[m].label, root.px(m), height - root.mB + 6)
        }
    }
    Txt { anchors.centerIn: parent; width: parent.width - 60; visible: root.n < 1; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
          text: root.emptyText; color: Theme.textMuted; font.pixelSize: Theme.fsSm }
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
