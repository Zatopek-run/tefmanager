import QtQuick

// Una priorità della settimana: barra colorata per gravità, clic = vai alla pagina collegata.
Rectangle {
    id: root
    property var info: ({})
    readonly property color tone: info.severity === "danger" ? Theme.bad : info.severity === "ok" ? Theme.good : Theme.warn
    implicitHeight: Math.max(40, label.implicitHeight + 20)
    radius: Theme.radiusMd
    color: ma.containsMouse ? "#1d2858" : Theme.surface2
    border.width: 1
    border.color: ma.containsMouse ? Theme.borderStrong : Theme.border
    Behavior on color { ColorAnimation { duration: 120 * Theme.animScale } }
    Rectangle { x: 0; y: 6; width: 3; height: parent.height - 12; radius: 1.5; color: root.tone }
    Txt { id: label
          anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; leftMargin: 14; rightMargin: 12 }
          text: info.text || ""; wrapMode: Text.WordWrap; font.weight: Font.Medium }
    MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: vm.navigate(info.target) }
}
