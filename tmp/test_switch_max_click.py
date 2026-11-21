"""Switch.set() 点击上限兜底的离线断言。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from module.base.button import Button
from module.base.timer import Timer
from module.ui.switch import Switch


class FakeDevice:
    def __init__(self):
        self.shots = 0

    def screenshot(self):
        self.shots += 1
        return None


class FakeMain:
    def __init__(self):
        self.device = FakeDevice()

    def appear(self, *args, **kwargs):
        return False


class AlwaysUnknownSwitch(Switch):
    """状态永远识别为 unknown 的开关，模拟画面根本不是战役页。"""

    def __init__(self):
        super().__init__('Mode_switch_test', is_selector=True)
        self.add_state('normal', check_button=Button(area=(0, 0, 1, 1), color=(0, 0, 0), button=(0, 0, 1, 1), name='T_NORMAL'))
        self.add_state('hard', check_button=Button(area=(0, 0, 1, 1), color=(0, 0, 0), button=(0, 0, 1, 1), name='T_HARD'))
        self.clicked = []

    def get(self, main=None, skip_first_screenshot=True):
        return 'unknown'

    def click(self, state, main=None):
        self.clicked.append(state)


def main():
    sw = AlwaysUnknownSwitch()
    sw.set_unknown_timer = Timer(0.01, count=1)
    sw.set_click_timer = Timer(0.01, count=1)
    sw.set_max_click = 6
    fake = FakeMain()

    result = sw.set('hard', main=fake)

    assert result is True, f'应该点击过（返回 True），实际 {result}'
    assert len(sw.clicked) == 6, f'应该在 6 次点击后停止，实际 {len(sw.clicked)}'
    assert all(x == 'hard' for x in sw.clicked), sw.clicked
    print(f'OK 上限兜底生效: 点击 {len(sw.clicked)} 次后返回，未死循环')

    # 正常情况下（第一次就到达目标）不应点击
    class DoneSwitch(AlwaysUnknownSwitch):
        def get(self, main=None, skip_first_screenshot=True):
            return 'hard'

    done = DoneSwitch()
    assert done.set('hard', main=fake) is False
    assert done.clicked == []
    print('OK 已到达目标状态时不点击')


if __name__ == '__main__':
    main()
