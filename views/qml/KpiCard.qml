import QtQuick
import QtQuick.Layouts

// Indicatore cliccabile (bilancio, prestigio, rosa, prossima gara): apre la pagina collegata.
Rectangle {
    id: root
    property var info: ({})
    property int order: 0
    property real appear: 1
    readonly property color toneColor: info.tone === "bad" ? Theme.bad : info.tone === "warn" ? Theme.warn : info.tone === "good" ? Theme.good : Theme.text

    implicitHeight: 100
    radius: Theme.radiusLg
    color: ma.containsMouse ? Theme.surface2 : Theme.surface
    border.width: 1
    border.color: ma.containsMouse ? Theme.accentDim : Theme.border
    opacity: appear
    transform: Translate { y: (1 - root.appear) * 14 }
    Behavior on color { ColorAnimation { duration: 140 * Theme.animScale } }
    Behavior on border.color { ColorAnimation { duration: 140 * Theme.animScale } }

    ColumnLayout {
        anchors { fill: parent; margins: Theme.sp4; topMargin: Theme.sp3; bottomMargin: Theme.sp3 }
        spacing: 2
        Txt { text: info.title || ""; font.pixelSize: Theme.fsXs; font.weight: Font.DemiBold; font.letterSpacing: 0.6; color: Theme.textMuted }
        Txt { text: info.value || ""; font.pixelSize: Theme.fsXxl; font.weight: Font.Bold; color: root.toneColor
              Behavior on color { ColorAnimation { duration: 200 * Theme.animScale } } }
        Txt { Layout.fillWidth: true; text: info.sub || ""; font.pixelSize: Theme.fsSm; color: Theme.textMuted; wrapMode: Text.WordWrap }
    }
    MouseArea {
        id: ma
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: vm.navigate(info.target)
    }
    Tip { visible: ma.containsMouse && (info.hint || "") !== ""; text: info.hint || ""; x: ma.mouseX + 12; y: ma.mouseY + 16 }

    Component.onCompleted: {
        if (Theme.animScale > 0) { appear = 0; enter.start() }
    }
    SequentialAnimation {
        id: enter
        PauseAnimation { duration: root.order * 60 * Theme.animScale }
        NumberAnimation { target: root; property: "appear"; from: 0; to: 1; duration: 380 * Theme.animScale; easing.type: Easing.OutCubic }
    }
}
