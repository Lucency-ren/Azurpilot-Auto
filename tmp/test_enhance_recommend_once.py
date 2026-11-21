"""「按推荐设置强化材料」只点一次的自测。

材料栏加载需要时间，过去 state_enhance_recommend 在没看到材料的瞬间
就退回 state_enhance_ready 再点一次推荐，所以每艘船都点两下。
现在只有等满 6 秒仍无材料才补点，正常情况下一次点击即可。
"""
import sys
from types import SimpleNamespace

sys.path.insert(0, r'D:\Alas\AzurPilot')

from module.retire import enhancement as E  # noqa: E402


class _Stub:
    def __init__(self, value=False):
        self.value = value

    def match(self, *a, **kw):
        return self.value

    def __bool__(self):
        return self.value


class _Obj(E.Enhancement):
    """_retire_keep_common_cv 依赖任务配置，这里固定关闭。"""

    @property
    def _retire_keep_common_cv(self):
        return False


def run(empty_polls=3):
    """empty_polls: 前几次轮询材料栏还是空的，之后出现材料。"""
    obj = _Obj.__new__(_Obj)
    obj.config = SimpleNamespace(Enhance_Count=1)
    obj.device = SimpleNamespace(
        image=None, click_record=[], screenshot=lambda: None,
        click_record_clear=lambda: None, click=lambda *a, **kw: None,
    )
    obj.info_bar_count = lambda: 0
    obj.interval_clear = lambda *a, **kw: None
    obj.interval_reset = lambda *a, **kw: None
    obj.wait_until_appear = lambda *a, **kw: None
    obj.equip_side_navbar_ensure = lambda upper=None, bottom=None: True
    obj._enhance_confirm = lambda *a, **kw: None
    obj.handle_popup_confirm = lambda *a, **kw: False
    obj.equip_view_next = lambda *a, **kw: False

    state = {'polls': 0, 'recommend_clicks': 0, 'confirm_seen': False}

    def slot_match(*a, **kw):
        state['polls'] += 1
        return state['polls'] <= empty_polls

    empty = _Stub()
    empty.match = slot_match

    recommend = _Stub(True)
    confirm = _Stub(True)
    equip_confirm = _Stub(True)

    saved = {}
    for name, value in (
        ('EMPTY_ENHANCE_SLOT_PLUS', empty), ('ENHANCE_RECOMMEND', recommend),
        ('ENHANCE_CONFIRM', confirm), ('EQUIP_CONFIRM', equip_confirm),
        ('DOCK_CHECK', _Stub(False)), ('BACK_ARROW', _Stub(False)),
        ('GET_ITEMS_1', _Stub(False)),
    ):
        saved[name] = getattr(E, name)
        setattr(E, name, value)

    def appear_then_click(button, *a, **kw):
        if button is recommend:
            state['recommend_clicks'] += 1
            return True
        if button is confirm:
            state['confirm_seen'] = True
            return True
        return False

    def appear(button, *a, **kw):
        if button is equip_confirm and state['confirm_seen']:
            state['confirm_seen'] = False
            return True
        return False

    obj.appear_then_click = appear_then_click
    obj.appear = appear

    try:
        # max_enhance=1：强化成功一次就收手，避免测试里在同一艘船上无限循环
        obj._enhance_choose(ship_count=1, stay=True, max_enhance=1)
    finally:
        for name, value in saved.items():
            setattr(E, name, value)
    return state['recommend_clicks']


def test_single_click():
    clicks = run(empty_polls=3)
    assert clicks == 1, f'材料加载期间不该重复点推荐，实际点了 {clicks} 次'
    print(f'OK recommend clicked once (材料延迟 3 次轮询)')


if __name__ == '__main__':
    test_single_click()
    print('ALL PASS')
