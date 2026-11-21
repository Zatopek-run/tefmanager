import QtQuick

// Semaforo delle notifiche: verde tutto ok, ambra da guardare, rosso dilemma o urgenza (il pallino pulsa).
Rectangle {
    id: root
    property string level: "ok"
    property string label: ""
    readonly property color tone: level === "danger" ? Theme.bad : level === "warn" ? Theme.warn : Theme.good

    implicitHeight: 28
    implicitWidth: row.implicitWidth + 28
    radius: height / 2
    color: Qt.rgba(tone.r, tone.g, tone.b, 0.13)
    border.width: 1
    border.color: Qt.rgba(tone.r, tone.g, tone.b, 0.5)
    Behavior on color { ColorAnimation { duration: 250 * Theme.animScale } }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 8
        Rectangle {
            id: dot
            width: 8; height: 8; radius: 4; color: root.tone
            anchors.verticalCenter: parent.verticalCenter
            SequentialAnimation on opacity {
                running: root.level === "danger" && Theme.animScale > 0
                loops: Animation.Infinite
                NumberAnimation { to: 0.25; duration: 700 }
                NumberAnimation { to: 1.0; duration: 700 }
            }
        }
        Txt { text: root.label; font.pixelSize: Theme.fsSm; font.weight: Font.DemiBold; color: root.tone }
    }
}
