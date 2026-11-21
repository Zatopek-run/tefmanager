import QtQuick
import QtQuick.Layouts

// Scheda del design system: titolo a sinistra, suggerimento a destra, corpo sotto (i figli vanno nel corpo).
Rectangle {
    id: root
    property string title: ""
    property string hint: ""
    property int order: 0          // ordine di ingresso: le schede arrivano una dopo l'altra
    property real appear: 1
    default property alias content: body.data

    color: Theme.surface
    radius: Theme.radiusLg
    border.width: 1
    border.color: Theme.border
    implicitHeight: col.implicitHeight + Theme.sp3 + Theme.sp4
    implicitWidth: 200
    opacity: appear
    transform: Translate { y: (1 - root.appear) * 14 }

    ColumnLayout {
        id: col
        anchors { left: parent.left; right: parent.right; top: parent.top; bottom: parent.bottom
                  leftMargin: Theme.sp4; rightMargin: Theme.sp4; topMargin: Theme.sp3; bottomMargin: Theme.sp4 }
        spacing: Theme.sp3
        RowLayout {
            Layout.fillWidth: true
            visible: root.title !== "" || root.hint !== ""
            Txt { text: root.title; font.weight: Font.Bold }
            Item { Layout.fillWidth: true }
            Txt { text: root.hint; color: Theme.textMuted; font.pixelSize: Theme.fsSm }
        }
        ColumnLayout {
            id: body
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.sp3
        }
    }

    Component.onCompleted: {
        if (Theme.animScale > 0) { appear = 0; enter.start() }
    }
    SequentialAnimation {
        id: enter
        PauseAnimation { duration: root.order * 70 * Theme.animScale }
        NumberAnimation { target: root; property: "appear"; from: 0; to: 1; duration: 420 * Theme.animScale; easing.type: Easing.OutCubic }
    }
}
