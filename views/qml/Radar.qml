import QtQuick

// Radar a N assi (0-100): poligono dell'atleta pieno, poligono della media dei compagni tratteggiato, anelli a 25/50/75/100.
Item {
    id: root
    property var axes: []        // [{label, value, avg}]
    property bool hasAvg: false
    property real reveal: 1
    implicitHeight: 240
    implicitWidth: 260

    onAxesChanged: { if (Theme.animScale > 0) { reveal = 0; grow.restart() } cv.requestPaint() }
    onHasAvgChanged: cv.requestPaint()
    onRevealChanged: cv.requestPaint()
    onWidthChanged: cv.requestPaint()
    onHeightChanged: cv.requestPaint()
    NumberAnimation { id: grow; target: root; property: "reveal"; from: 0; to: 1; duration: 650 * Theme.animScale; easing.type: Easing.OutCubic }

    function rgba(hex, a) { var c = Qt.color(hex); return "rgba(" + Math.round(c.r * 255) + "," + Math.round(c.g * 255) + "," + Math.round(c.b * 255) + "," + a + ")" }

    Canvas {
        id: cv
        anchors.fill: parent
        renderTarget: Canvas.Image
        renderStrategy: Canvas.Immediate
        Component.onCompleted: requestPaint()
        onPaint: {
            var ctx = getContext("2d"); ctx.reset()
            var n = root.axes.length
            if (n < 3) return
            var cx = width / 2, cy = height / 2 + 4
            var R = Math.min(width / 2 - 80, height / 2 - 30)
            function pt(i, v) { var a = -Math.PI / 2 + 2 * Math.PI * i / n; return [cx + Math.cos(a) * R * v / 100, cy + Math.sin(a) * R * v / 100] }
            // anelli e raggi
            ctx.lineWidth = 1
            var rings = [25, 50, 75, 100]
            for (var r = 0; r < rings.length; r++) {
                ctx.strokeStyle = r === rings.length - 1 ? Theme.borderStrong : Theme.border
                ctx.beginPath()
                for (var i = 0; i <= n; i++) { var p = pt(i % n, rings[r]); if (i === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]) }
                ctx.stroke()
            }
            ctx.strokeStyle = Theme.border
            for (var k = 0; k < n; k++) { var e = pt(k, 100); ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(e[0], e[1]); ctx.stroke() }
            // media dei compagni (tratteggio)
            if (root.hasAvg) {
                ctx.setLineDash([4, 4]); ctx.strokeStyle = Theme.textMuted; ctx.lineWidth = 1.6
                ctx.beginPath()
                for (var a = 0; a <= n; a++) { var q = pt(a % n, (root.axes[a % n].avg || 0) * root.reveal); if (a === 0) ctx.moveTo(q[0], q[1]); else ctx.lineTo(q[0], q[1]) }
                ctx.stroke(); ctx.setLineDash([])
            }
            // atleta
            ctx.beginPath()
            for (var b = 0; b <= n; b++) { var s = pt(b % n, root.axes[b % n].value * root.reveal); if (b === 0) ctx.moveTo(s[0], s[1]); else ctx.lineTo(s[0], s[1]) }
            ctx.closePath()
            ctx.fillStyle = root.rgba(Theme.accent, 0.26); ctx.fill()
            ctx.strokeStyle = Theme.accent; ctx.lineWidth = 2.4; ctx.lineJoin = "round"; ctx.stroke()
            for (var d = 0; d < n; d++) {
                var dp = pt(d, root.axes[d].value * root.reveal)
                ctx.fillStyle = Theme.accent; ctx.strokeStyle = Theme.surface; ctx.lineWidth = 2
                ctx.beginPath(); ctx.arc(dp[0], dp[1], 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke()
            }
            // etichette
            ctx.font = "600 12px sans-serif"; ctx.textBaseline = "middle"
            for (var m = 0; m < n; m++) {
                var lp = pt(m, 100)
                var ang = -Math.PI / 2 + 2 * Math.PI * m / n
                var lx = lp[0] + Math.cos(ang) * 14, ly = lp[1] + Math.sin(ang) * 12
                ctx.textAlign = Math.cos(ang) > 0.3 ? "left" : (Math.cos(ang) < -0.3 ? "right" : "center")
                ctx.fillStyle = Theme.textMuted
                ctx.fillText(root.axes[m].label, lx, ly - 7)
                ctx.fillStyle = Theme.text; ctx.font = "700 13px sans-serif"
                ctx.fillText(root.axes[m].value, lx, ly + 8)
                ctx.font = "600 12px sans-serif"
            }
        }
    }
}
