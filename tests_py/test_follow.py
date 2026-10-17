"""跟随模式里摆位置的计算（纯函数，不碰真实窗口）。"""

from claude_girl.follow import offsets, place

HOST = (100, 50, 1100, 850)  # 1000 × 800


def test_place_right_anchor():
    assert place(HOST, (200, 360), "right", 12, 140) == (1100 - 12 - 200, 850 - 140 - 360)


def test_place_left_anchor():
    assert place(HOST, (200, 360), "left", 30, 0) == (130, 490)


def test_place_clamped_inside_host():
    # 离边太远会跑出窗口：收回到窗口里
    assert place(HOST, (200, 360), "right", 5000, 5000) == (100, 50)
    # 桌宠比窗口还高：顶边对齐
    assert place(HOST, (200, 1000), "right", 0, 0)[1] == 50


def test_offsets_roundtrip():
    for anchor, gx, gy in (("right", 12, 140), ("left", 40, 20)):
        x, y = place(HOST, (200, 360), anchor, gx, gy)
        assert offsets(HOST, (x, y, x + 200, y + 360)) == (anchor, gx, gy)


def test_offsets_picks_nearer_side():
    assert offsets(HOST, (150, 400, 350, 760))[0] == "left"
    assert offsets(HOST, (800, 400, 1000, 760))[0] == "right"
