import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

// Parte grafica della scheda atleta (G.2): radar, potenziale, condizione, caratteristiche, ultime gare, confronto. Disegna solo `vm.snapshot`.
Rectangle {
    id: root
    color: "transparent"
    property var d: vm.snapshot

    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: width
        contentHeight: page.implicitHeight + Theme.sp3
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
            contentItem: Rectangle { implicitWidth: 6; radius: 3; color: Theme.borderStrong; opacity: parent.active || parent.hovered ? 1 : 0.55 }
            background: Item {}
        }

        ColumnLayout {
            id: page
            width: flick.width - 12
            spacing: Theme.sp3

            RowLayout {
                Layout.fillWidth: true; spacing: Theme.sp3
                Card {
                    Layout.preferredWidth: 340; Layout.fillHeight: true
                    title: "Profilo"; hint: d.radar.hasAvg ? "— — media dei compagni" : ""; order: 0
                    Radar { Layout.fillWidth: true; Layout.preferredHeight: 240; axes: d.radar.axes; hasAvg: d.radar.hasAvg }
                    Txt { Layout.fillWidth: true; visible: d.radar.hasAvg; text: d.radar.avgLabel; font.pixelSize: Theme.fsXs; color: Theme.textFaint; horizontalAlignment: Text.AlignHCenter }
                }
                ColumnLayout {
                    Layout.fillWidth: true; Layout.fillHeight: true; spacing: Theme.sp3
                    Card {
                        Layout.fillWidth: true
                        title: "Potenziale"; hint: "★".repeat(d.potential.stars) + "☆".repeat(5 - d.potential.stars); order: 1
                        Rectangle {
                            Layout.fillWidth: true; Layout.preferredHeight: 14; radius: 7; color: Theme.bg
                            Rectangle {
                                height: parent.height; radius: 7
                                width: parent.width * d.potential.pct / 100
                                gradient: Gradient { orientation: Gradient.Horizontal
                                    GradientStop { position: 0.0; color: Theme.accentDim }
                                    GradientStop { position: 1.0; color: Theme.accent } }
                                Behavior on width { NumberAnimation { duration: 700 * Theme.animScale; easing.type: Easing.OutCubic } }
                            }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Txt { text: "OVR " + d.potential.overall; font.weight: Font.Bold }
                            Item { Layout.fillWidth: true }
                            Txt { text: "Potenziale " + d.potential.potential; font.weight: Font.Bold }
                        }
                        Txt { Layout.fillWidth: true; text: d.potential.text; color: Theme.textMuted; font.pixelSize: Theme.fsSm; wrapMode: Text.WordWrap }
                    }
                    Card {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        title: "Condizione"; order: 2
                        Repeater { model: d.condition; BarRow { Layout.fillWidth: true; info: modelData } }
                        Item { Layout.fillHeight: true }
                    }
                }
            }

            Card {
                Layout.fillWidth: true
                title: "Caratteristiche"; order: 3
                RowLayout {
                    Layout.fillWidth: true; spacing: Theme.sp5
                    ColumnLayout { Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; spacing: 8
                        Txt { text: "FISICO"; font.pixelSize: Theme.fsXs; font.weight: Font.DemiBold; color: Theme.textFaint; font.letterSpacing: 0.6 }
                        Repeater { model: d.physical; BarRow { Layout.fillWidth: true; info: modelData } } }
                    ColumnLayout { Layout.fillWidth: true; Layout.alignment: Qt.AlignTop; spacing: 8
                        Txt { text: "TECNICA"; font.pixelSize: Theme.fsXs; font.weight: Font.DemiBold; color: Theme.textFaint; font.letterSpacing: 0.6 }
                        Repeater { model: d.technical; BarRow { Layout.fillWidth: true; info: modelData } } }
                }
            }

            Card {
                Layout.fillWidth: true
                title: "Ultime gare"; hint: d.performance.summary; order: 4
                PerformanceChart { Layout.fillWidth: true; Layout.preferredHeight: 170; points: d.performance.points; emptyText: d.performance.emptyText }
                RowLayout {
                    visible: d.performance.points.length > 0; spacing: 16
                    Row { spacing: 6; Rectangle { width: 9; height: 9; radius: 4.5; color: Theme.good; anchors.verticalCenter: parent.verticalCenter } Txt { text: "vittoria"; font.pixelSize: Theme.fsXs; color: Theme.textMuted } }
                    Row { spacing: 6; Rectangle { width: 8; height: 8; rotation: 45; color: Theme.warn; anchors.verticalCenter: parent.verticalCenter } Txt { text: "primato personale"; font.pixelSize: Theme.fsXs; color: Theme.textMuted } }
                    Row { spacing: 6; Txt { text: "✕"; color: Theme.bad; font.pixelSize: Theme.fsXs; font.weight: Font.Bold } Txt { text: "ritirato"; font.pixelSize: Theme.fsXs; color: Theme.textMuted } }
                }
            }

            Card {
                Layout.fillWidth: true
                title: d.comparison.title; hint: d.comparison.text; order: 5
                ComparisonList { Layout.fillWidth: true; comparison: d.comparison }
            }
        }
    }
}
