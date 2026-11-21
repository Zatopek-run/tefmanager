import QtQuick

// Forma e fatica medie della rosa: due linee su scala 0-100, area sotto la forma, valori al passaggio del mouse.
Item {
    id: root
    property var form: []
    property var fatigue: []
    property var tips: []
    property string emptyText: ""
    property real reveal: 1
    property int hoverIdx: -1
    readonly property int n: form.length
    readonly property int shown: hoverIdx >= 0 && hoverIdx < n ? hoverIdx : n - 1
    readonly property real mL: 34
    readonly property real mR: 18
    readonly property real mT: 32
    readonly property real mB: 24

    implicitHeight: 200

    function px(i) { return n > 1 ? mL + (width - mL - mR) * i / (n - 1) : mL + (width - mL - mR) / 2 }
    function py(v) { return mT + (height - mT - mB) * (1 - Math.max(0, Math.min(100, v)) / 100) }
    function rgba(hex, a) { var c = Qt.color(hex); return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }

    onFormChanged: { if (Theme.animScale > 0 && n > 1) { reveal = 0; draw.restart() } cv.requestPaint() }
    onFatigueChanged: cv.requestPaint()
    onHoverIdxChanged: cv.requestPaint()
    onRevealChanged: cv.requestPaint()
    onWidthChanged: cv.requestPaint()
    onHeightChanged: cv.requestPaint()
    NumberAnimation { id: draw; target: root; property: "reveal"; from: 0; to: 1; duration: 700 * Theme.animScale; easing.type: Easing.OutCubic }

    Canvas {
        id: cv
        anchors.fill: parent
        renderTarget: Canvas.Image   // il default (FBO) non esiste nel backend software
        renderStrategy: Canvas.Immediate
        Component.onCompleted: requestPaint()
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var plotB = height - root.mB
            ctx.font = "11px sans-serif"
            ctx.textAlign = "right"
            ctx.textBaseline = "middle"
            var steps = [0, 25, 50, 75, 100]
            for (var s = 0; s < steps.length; s++) {
                var y = root.py(steps[s])
                ctx.strokeStyle = Theme.border
                ctx.lineWidth = 1
                ctx.setLineDash(steps[s] === 0 || steps[s] === 100 ? [] : [2, 4])
                ctx.beginPath(); ctx.moveTo(root.mL, y + 0.5); ctx.lineTo(width - root.mR, y + 0.5); ctx.stroke()
                ctx.fillStyle = Theme.textFaint
                ctx.fillText(steps[s], root.mL - 8, y)
            }
            ctx.setLineDash([])
            if (root.n < 1) return
            ctx.save()
            ctx.beginPath(); ctx.rect(0, 0, root.mL + (width - root.mL) * root.reveal, height); ctx.clip()
            if (root.n > 1) {
                var g = ctx.createLinearGradient(0, root.mT, 0, plotB)
                g.addColorStop(0, root.rgba(Theme.accent, 0.30))
                g.addColorStop(1, root.rgba(Theme.accent, 0.0))
                ctx.beginPath(); ctx.moveTo(root.px(0), plotB)
                for (var i = 0; i < root.n; i++) ctx.lineTo(root.px(i), root.py(root.form[i]))
                ctx.lineTo(root.px(root.n - 1), plotB); ctx.closePath()
                ctx.fillStyle = g; ctx.fill()
            }
            var series = [[root.fatigue, Theme.warn], [root.form, Theme.accent]]
            for (var k = 0; k < series.length; k++) {
                var vals = series[k][0]
                ctx.strokeStyle = series[k][1]; ctx.lineWidth = 2.4; ctx.lineJoin = "round"; ctx.lineCap = "round"
                ctx.beginPath()
                for (var j = 0; j < root.n; j++) { if (j === 0) ctx.moveTo(root.px(j), root.py(vals[j])); else ctx.lineTo(root.px(j), root.py(vals[j])) }
                ctx.stroke()
            }
            ctx.restore()
            var idx = root.shown
            if (root.hoverIdx >= 0) {
                ctx.strokeStyle = root.rgba(Theme.text, 0.25); ctx.lineWidth = 1
                ctx.beginPath(); ctx.moveTo(root.px(idx), root.mT); ctx.lineTo(root.px(idx), plotB); ctx.stroke()
            }
            for (var m = 0; m < series.length; m++) {
                ctx.fillStyle = series[m][1]; ctx.strokeStyle = Theme.surface; ctx.lineWidth = 2
                ctx.beginPath(); ctx.arc(root.px(idx), root.py(series[m][0][idx]), 4.5, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
            }
            ctx.fillStyle = Theme.textFaint; ctx.font = "11px sans-serif"; ctx.textBaseline = "top"
            ctx.textAlign = "left"; ctx.fillText(root.n > 1 ? (root.n - 1) + " sett. fa" : "", root.mL - 10, plotB + 6)
            ctx.textAlign = "right"; ctx.fillText("ultima", width - root.mR + 10, plotB + 6)
        }
    }

    // legenda con i valori del punto evidenziato
    Row {
        x: root.mL; y: 4
        spacing: 18
        visible: root.n > 0
        Row { spacing: 6
            Rectangle { width: 8; height: 8; radius: 4; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
            Txt { text: "Forma " + (root.n > 0 ? Math.round(root.form[root.shown]) : ""); font.pixelSize: Theme.fsSm; font.weight: Font.DemiBold } }
        Row { spacing: 6
            Rectangle { width: 8; height: 8; radius: 4; color: Theme.warn; anchors.verticalCenter: parent.verticalCenter }
            Txt { text: "Fatica " + (root.n > 0 ? Math.round(root.fatigue[root.shown]) : ""); font.pixelSize: Theme.fsSm; font.weight: Font.DemiBold } }
    }
    Txt {
        anchors { centerIn: parent; verticalCenterOffset: 4 }
        width: parent.width - 80
        visible: root.n < 1
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
        text: root.emptyText
        color: Theme.textMuted
        font.pixelSize: Theme.fsSm
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.n > 0
        onPositionChanged: (m) => {
            var frac = (m.x - root.mL) / Math.max(1, width - root.mL - root.mR)
            root.hoverIdx = root.n > 1 ? Math.max(0, Math.min(root.n - 1, Math.round(frac * (root.n - 1)))) : 0
        }
        onExited: root.hoverIdx = -1
    }
    Tip { visible: ma.containsMouse && root.hoverIdx >= 0 && root.hoverIdx < root.tips.length; text: root.hoverIdx >= 0 && root.hoverIdx < root.tips.length ? root.tips[root.hoverIdx] : ""
          x: ma.mouseX + 12; y: ma.mouseY + 16 }
}
