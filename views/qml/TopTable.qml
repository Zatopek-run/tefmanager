import QtQuick
import QtQuick.Layouts

// I migliori atleti: nomi interi, stato a «pillola»; doppio clic = Scheda Atleta.
ColumnLayout {
    id: root
    property var table: ({ rows: [], emptyText: "" })
    spacing: 0
    readonly property var colW: [0, 120, 56, 64, 64, 140]   // la prima colonna prende il resto

    RowLayout {
        Layout.fillWidth: true; Layout.preferredHeight: 30; spacing: 0
        Repeater {
            model: ["Atleta", "Disciplina", "OVR", "Forma", "Fatica", "Stato"]
            Txt {
                Layout.fillWidth: index === 0; Layout.preferredWidth: root.colW[index]
                text: modelData; font.pixelSize: Theme.fsXs; font.weight: Font.DemiBold; font.letterSpacing: 0.4; color: Theme.textMuted
                horizontalAlignment: index === 0 ? Text.AlignLeft : Text.AlignHCenter
                leftPadding: index === 0 ? 10 : 0
            }
        }
    }
    Rectangle { Layout.fillWidth: true; height: 1; color: Theme.borderStrong }

    Txt {
        Layout.fillWidth: true; Layout.topMargin: 12; Layout.bottomMargin: 12
        visible: table.rows.length === 0
        text: table.emptyText; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; color: Theme.textMuted
    }

    Repeater {
        model: table.rows
        Rectangle {
            id: row
            Layout.fillWidth: true; Layout.preferredHeight: 40
            color: rma.containsMouse ? Theme.surface2 : "transparent"
            Behavior on color { ColorAnimation { duration: 100 * Theme.animScale } }
            readonly property color badge: modelData.level === "danger" ? Theme.bad : modelData.level === "warn" ? Theme.warn : Theme.good
            RowLayout {
                anchors.fill: parent; spacing: 0
                Txt { Layout.fillWidth: true; Layout.preferredWidth: 0; text: modelData.name; elide: Text.ElideRight; leftPadding: 10 }
                Txt { Layout.preferredWidth: root.colW[1]; horizontalAlignment: Text.AlignHCenter; text: modelData.specialty }
                Txt { Layout.preferredWidth: root.colW[2]; horizontalAlignment: Text.AlignHCenter; text: modelData.ovr; font.weight: Font.DemiBold }
                Txt { Layout.preferredWidth: root.colW[3]; horizontalAlignment: Text.AlignHCenter; text: modelData.form }
                Txt { Layout.preferredWidth: root.colW[4]; horizontalAlignment: Text.AlignHCenter; text: modelData.fatigue }
                Item {
                    Layout.preferredWidth: root.colW[5]; Layout.fillHeight: true
                    Rectangle {
                        anchors.centerIn: parent
                        width: statusText.implicitWidth + 22; height: 22; radius: 11
                        color: Qt.rgba(row.badge.r, row.badge.g, row.badge.b, 0.16)
                        Txt { id: statusText; anchors.centerIn: parent; text: modelData.status; font.pixelSize: Theme.fsSm; font.weight: Font.DemiBold; color: row.badge }
                    }
                }
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.border }
            MouseArea { id: rma; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onDoubleClicked: vm.openAthlete(modelData.id) }
        }
    }
}
