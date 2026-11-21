"""装备/强化页左右滑动切换舰船的自测（不连模拟器）。

重点验证重复舰船场景：滑动后画面完全一样时不能立刻判定「滑不动」，
而是先按「已切换」返回（让上层试一次强化），连续超过 max_same 次都没
变化才返回 False（此时认定滑到列表末尾）。
"""
import sys
from types import SimpleNamespace

sys.path.insert(0, r'D:\Alas\AzurPilot')

from module.equipment import equipment as EQ  # noqa: E402


class _FakeSwipeCheck:
    def __init__(self, same):
        self.same = same

    def load_color(self, image):
        pass

    def match(self, image):
        return self.same


def make_obj(same):
    obj = EQ.Equipment.__new__(EQ.Equipment)
    obj.swipes = []
    obj.device = SimpleNamespace(
        image=object(),
        screenshot=lambda: None,
        swipe_vector=lambda **kw: obj.swipes.append(kw),
    )
    obj.handle_info_bar = lambda: None
    obj.handle_popup_confirm = lambda *a, **kw: False
    check = object()
    # 只有「滑动完成」的检测按钮出现，退役装备确认弹窗不出现
    obj.appear = lambda button, **kw: button is check

    saved = EQ.SWIPE_CHECK
    EQ.SWIPE_CHECK = _FakeSwipeCheck(same)
    try:
        results = [obj._ship_view_swipe(distance=-180, check_button=check, max_same=3) for _ in range(6)]
    finally:
        EQ.SWIPE_CHECK = saved
    return results, len(obj.swipes)


def test_duplicate_ships_not_skipped():
    """画面一直没变：前 3 次仍按「已切换」返回（让上层强化），第 4 次才放弃。"""
    results, count = make_obj(same=True)
    assert results[:4] == [True, True, True, False], results
    assert results[4:] == [True, True], results  # 放弃后计数归零，重新开始
    assert count == 6, count  # 每次调用只滑一次
    print(f'OK duplicate treated as moved: {results}')


def test_new_ship_detected():
    """画面变化时一次滑动即成功，并清零重复计数。"""
    results, count = make_obj(same=False)
    assert results == [True] * 6, results
    assert count == 6, count
    print('OK new ship detected')


if __name__ == '__main__':
    test_duplicate_ships_not_skipped()
    test_new_ship_detected()
    print('ALL PASS')
