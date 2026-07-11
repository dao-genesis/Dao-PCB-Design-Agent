"""Tests for electrical validation — design intelligence beyond DRC."""

from dao_kicad.core.manipulate import BoardBuilder
from dao_kicad.core.electrical import ElectricalValidator, ElectricalReport


class TestElectricalValidator:
    def _make_stm32_board(self, num_caps=0, bulk_cap=False):
        """Build a board with an STM32 and optional decoupling."""
        builder = BoardBuilder.new(copper_layers=2, width_mm=40, height_mm=30)
        builder.add_nets("3V3", "GND")
        builder.place("Package_QFP", "LQFP-48_7x7mm_P0.5mm", "U1", 20, 15,
                      value="STM32F103")
        builder.assign_net("U1", "1", "3V3")
        builder.assign_net("U1", "2", "GND")

        for i in range(num_caps):
            ref = f"C{i+1}"
            builder.place("Capacitor_SMD", "C_0402_1005Metric", ref,
                         18 + i * 2, 13, value="100nF")
            builder.assign_net(ref, "1", "3V3")
            builder.assign_net(ref, "2", "GND")

        if bulk_cap:
            ref = f"C{num_caps+1}"
            builder.place("Capacitor_SMD", "C_0805_2012Metric", ref,
                         14, 15, value="10uF")
            builder.assign_net(ref, "1", "3V3")
            builder.assign_net(ref, "2", "GND")

        return builder

    def test_missing_decoupling(self):
        builder = self._make_stm32_board(num_caps=0)
        ev = ElectricalValidator(builder.board)
        report = ev.validate_all()
        # Should flag missing decoupling for STM32
        decoupling = [i for i in report.issues if i.category == "decoupling"]
        assert len(decoupling) > 0
        assert any(i.severity == "critical" for i in decoupling)

    def test_sufficient_decoupling(self):
        builder = self._make_stm32_board(num_caps=3, bulk_cap=True)
        ev = ElectricalValidator(builder.board)
        report = ev.validate_all()
        # Should not flag decoupling as critical
        critical_decoupling = [i for i in report.issues
                              if i.category == "decoupling" and i.severity == "critical"]
        assert len(critical_decoupling) == 0

    def test_no_ground_net(self):
        builder = BoardBuilder.new(copper_layers=2, width_mm=20, height_mm=15)
        builder.add_nets("VCC")
        builder.place("Resistor_SMD", "R_0402_1005Metric", "R1", 10, 8)
        ev = ElectricalValidator(builder.board)
        report = ev.validate_all()
        power_issues = [i for i in report.issues if i.category == "power"]
        assert any("ground" in i.description.lower() for i in power_issues)

    def test_report_summary(self):
        report = ElectricalReport()
        assert report.critical_count == 0
        assert "0 critical" in report.summary()


class TestUSBValidation:
    def test_usb_c_no_pulldown(self):
        builder = BoardBuilder.new(copper_layers=2, width_mm=30, height_mm=20)
        builder.add_nets("GND", "VBUS", "USB_D+", "USB_D-")
        builder.place("Connector_USB", "USB_C_Receptacle_GCT_USB4110", "J1",
                      5, 10, value="USB-C")
        builder.assign_net("J1", "A1", "GND")

        ev = ElectricalValidator(builder.board)
        report = ev.validate_all()
        usb_issues = [i for i in report.issues if i.category == "usb"]
        # Should warn about missing CC pull-downs
        assert len(usb_issues) > 0
