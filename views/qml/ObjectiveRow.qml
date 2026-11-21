import QtQuick
import QtQuick.Layouts

// Un obiettivo del Board: spunta vera (cerchio pieno con segno se fatto, anello vuoto altrimenti).
RowLayout {
    id: root
    property var info: ({})
    readonly property bool alert: info.kind === "warn" || info.kind === "fired"
    spacing: 10
    Canvas {
        Layout.alignment: Qt.AlignTop
        Layout.preferredWidth: 20; Layout.preferredHeight: 20
        renderTarget: Canvas.Image
        renderStrategy: Canvas.Immediate
        onPaint: {
            var ctx = getContext("2d"); ctx.reset()
            if (root.alert) {
                ctx.fillStyle = Theme.bad; ctx.beginPath(); ctx.arc(10, 10, 8.5, 0, Math.PI * 2); ctx.fill()
                ctx.fillStyle = Theme.bg; ctx.font = "bold 13px sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText("!", 10, 11)
            } else if (root.info.done) {
                ctx.fillStyle = Theme.good; ctx.beginPath(); ctx.arc(10, 10, 8.5, 0, Math.PI * 2); ctx.fill()
                ctx.strokeStyle = Theme.bg; ctx.lineWidth = 2; ctx.lineCap = "round"; ctx.lineJoin = "round"
                ctx.beginPath(); ctx.moveTo(6, 10.5); ctx.lineTo(9, 13.5); ctx.lineTo(14, 7); ctx.stroke()
            } else {
                ctx.strokeStyle = Theme.textFaint; ctx.lineWidth = 1.6
                ctx.beginPath(); ctx.arc(10, 10, 8, 0, Math.PI * 2); ctx.stroke()
            }
        }
        Component.onCompleted: requestPaint()
    }
    Txt {
        Layout.fillWidth: true
        text: info.text || ""
        wrapMode: Text.WordWrap
        color: root.alert ? Theme.bad : (info.done ? Theme.textMuted : Theme.text)
    }
}
