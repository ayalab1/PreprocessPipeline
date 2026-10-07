import numpy as np
import pytest

from src.preprocess.io import (
    _flex_g5_layout_coords,
    _flex_g5_ver2_layout_coords,
    build_channel_map_data,
)


@pytest.mark.parametrize("n_channels", [32, 64, 128, 256])
def test_flex_g5_ver2_preserves_legacy_positions_in_spatial_order(n_channels):
    x, y = _flex_g5_ver2_layout_coords(n_channels, 0)
    np.testing.assert_allclose(x[:5], [0, 0, -21.5, 21.5, 0])
    np.testing.assert_allclose(y[:5], [800, 0, -15, -15, -30])
    assert (x[31], y[31]) == (0, -300)
    for start in range(0, n_channels, 32):
        center = (start // 64) * 1000 + ((start // 32) % 2) * 80
        np.testing.assert_allclose(x[start:start + 32] - center, x[:32])
        np.testing.assert_allclose(y[start:start + 32], y[:32])

    legacy_x, legacy_y = _flex_g5_layout_coords(max(64, n_channels), 0)
    if n_channels == 32:
        left_half = legacy_x < 40
        legacy_x, legacy_y = legacy_x[left_half], legacy_y[left_half]
    assert sorted(zip(x, y)) == sorted(zip(legacy_x, legacy_y))
    shifted_x, shifted_y = _flex_g5_ver2_layout_coords(n_channels, 2)
    np.testing.assert_allclose(shifted_x, x + 2000)
    np.testing.assert_allclose(shifted_y, y)


def _flex_g5_ver2_xml_groups():
    # Actual PFC2 XML order. The second shank's top contact is 62 (not 65).
    first = [
        1, 3, 32, 0, 30, 29, 5, 2, 28, 7, 27, 26, 4, 9, 25, 6,
        24, 23, 11, 8, 22, 13, 21, 20, 10, 15, 19, 12, 18, 17, 16, 14,
    ]
    second = [
        62, 33, 63, 31, 60, 61, 35, 34, 58, 37, 59, 56, 36, 39, 57, 38,
        54, 55, 41, 40, 52, 43, 53, 50, 42, 45, 51, 44, 48, 49, 47, 46,
    ]
    return [[ch + offset for ch in group] for offset in range(0, 256, 64)
            for group in (first, second)]


def _write_flex_g5_ver2_xml(path, groups, skipped=()):
    groups_xml = []
    for group in groups:
        channels = "".join(
            f'<channel skip="{int(ch in skipped)}">{ch}</channel>' for ch in group
        )
        groups_xml.append(f"<group>{channels}</group>")
    path.write_text(
        "<session><generalInfo><description>flex-G5 ver2</description></generalInfo>"
        "<anatomicalDescription><channelGroups>" + "".join(groups_xml)
        + "</channelGroups></anatomicalDescription></session>", encoding="utf-8",
    )


def test_flex_g5_ver2_uses_xml_order_for_all_eight_shanks(tmp_path):
    groups = _flex_g5_ver2_xml_groups()
    xml = tmp_path / "session.xml"
    _write_flex_g5_ver2_xml(xml, groups, skipped=[32, 62, 255])
    data = build_channel_map_data(
        tmp_path, xml_path=xml, reject_channels=[0],
        probe_assignments=[
            {"type": "flex-G5 ver2", "groups": [i], "x_offset": i * 1000}
            for i in range(8)
        ],
    )
    ids = data["chanMap0ind"].ravel().astype(int)
    x, y = data["xcoords"].ravel(), data["ycoords"].ravel()
    np.testing.assert_array_equal(ids, np.arange(256))
    np.testing.assert_array_equal(data["chanMap"].ravel(), ids + 1)
    assert ids[y == 800].tolist() == [1, 62, 65, 126, 129, 190, 193, 254]
    for i, channels in enumerate(groups):
        np.testing.assert_allclose(x[channels] - i * 1000, x[groups[0]])
        np.testing.assert_allclose(y[channels], y[groups[0]])
        np.testing.assert_array_equal(data["probe_ids"].ravel()[channels], i + 1)
        assert x[channels[0]] == i * 1000
        assert y[channels[-1]] == -300
    np.testing.assert_allclose(x[[1, 3, 32, 0, 14]], [0, 0, -21.5, 21.5, 0])
    np.testing.assert_allclose(y[[1, 3, 32, 0, 14]], [800, 0, -15, -15, -300])
    # Bad channels keep their positions and IDs; they only change the mask.
    assert ids[data["connected"].ravel() == 0].tolist() == [0, 32, 62, 255]


def test_flex_g5_ver2_pairs_shanks_and_tiles_merged_xml_groups(tmp_path):
    groups = _flex_g5_ver2_xml_groups()
    xml = tmp_path / "session.xml"
    _write_flex_g5_ver2_xml(xml, groups)
    # Description-based selection uses the same geometry as an explicit assignment.
    data = build_channel_map_data(tmp_path, xml_path=xml)
    x, y = data["xcoords"].ravel(), data["ycoords"].ravel()
    tops = [g[0] for g in groups]
    np.testing.assert_allclose(x[tops], [-1540, -1460, -540, -460, 460, 540, 1460, 1540])
    np.testing.assert_allclose(y[tops], np.full(8, 800))
    np.testing.assert_array_equal(data["kcoords"].ravel()[tops], [1, 1, 2, 2, 3, 3, 4, 4])

    # A merged XML group lists each complete shank consecutively, without
    # wrapping device IDs modulo 64 onto already occupied positions.
    _write_flex_g5_ver2_xml(xml, [[ch for g in groups for ch in g]])
    merged = build_channel_map_data(tmp_path, xml_path=xml)
    for key in ("xcoords", "ycoords", "kcoords", "chanMap0ind"):
        np.testing.assert_array_equal(merged[key], data[key])
    assert len(set(zip(x, y))) == 256


def test_flex_g5_ver2_follows_xml_reordering_while_legacy_keeps_id_mapping(tmp_path):
    groups = _flex_g5_ver2_xml_groups()[:2]
    xml = tmp_path / "session.xml"

    def build(layout):
        return build_channel_map_data(
            tmp_path, xml_path=xml,
            probe_assignments=[{"type": layout, "groups": [0, 1], "x_offset": 0}],
        )

    _write_flex_g5_ver2_xml(xml, groups)
    legacy_before, ver2_before = build("flex-G5"), build("flex-G5 ver2")
    groups[1][0], groups[1][1] = groups[1][1], groups[1][0]
    _write_flex_g5_ver2_xml(xml, groups)
    legacy_after, ver2_after = build("flex-G5"), build("flex-G5 ver2")
    for key in ("xcoords", "ycoords", "chanMap0ind", "connected"):
        np.testing.assert_array_equal(legacy_before[key], legacy_after[key])
    assert ver2_before["ycoords"].ravel()[62] == 800
    assert ver2_after["ycoords"].ravel()[33] == 800
    assert ver2_after["ycoords"].ravel()[62] == 0


def test_flex_g5_ver2_rejects_incomplete_shanks(tmp_path):
    xml = tmp_path / "session.xml"
    _write_flex_g5_ver2_xml(xml, [list(range(31)), list(range(31, 64))])
    with pytest.raises(ValueError, match="group 0 has 31 channels"):
        build_channel_map_data(tmp_path, xml_path=xml)
