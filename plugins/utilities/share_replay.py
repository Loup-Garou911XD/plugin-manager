# ba_meta require api 7
from __future__ import annotations
from typing import TYPE_CHECKING, cast
if TYPE_CHECKING:
    from typing import Any, Sequence, Callable, List, Dict, Tuple, Optional, Union

from os import listdir, mkdir, path, sep
from shutil import copy, copytree

import ba
import _ba
from enum import Enum
from bastd.ui.tabs import TabRow
from bastd.ui.confirm import ConfirmWindow
from bastd.ui.watch import WatchWindow
from bastd.ui.popup import PopupWindow

# mod by ʟօʊքɢǟʀօʊ
# export replays to mods folder and share with your friends or have a backup

title = "SHARE REPLAY"
internal_dir = _ba.get_replays_dir()+sep
external_dir = path.join(_ba.env()["python_directory_user"], "replays"+sep)
uiscale = ba.app.ui.uiscale

# colors
pink = (1, 0.2, 0.8)
green = (0.4, 1, 0.4)
red = (1, 0, 0)
blue = (0.26, 0.65, 0.94)
blue_highlight = (0.4, 0.7, 1)

if not path.exists(external_dir):
    mkdir(external_dir)
    Print("You are ready to share replays", color=pink)


def Print(*args, color=None, top=None):
    out = ""
    for arg in args:
        a = str(arg)
        out += a
    ba.screenmessage(out, color=color, top=top)


def cprint(*args):
    out = ""
    for arg in args:
        a = str(arg)
        out += a
    _ba.chatmessage(out)


def override(cls: ClassType) -> Callable[[MethodType], MethodType]:
    def decorator(newfunc: MethodType) -> MethodType:
        funcname = newfunc.__code__.co_name
        if hasattr(cls, funcname):
            oldfunc = getattr(cls, funcname)
            setattr(cls, f'_old_{funcname}', oldfunc)

        setattr(cls, funcname, newfunc)
        return newfunc

    return decorator

class CommonUtilities:
     
    def sync_confirmation(self):
        ConfirmWindow(text="WARNING:\nreplays with same name in mods folder\n will be overwritten",
                      action=self.sync, cancel_is_selected=True)

    def sync(self):
        internal_list = listdir(internal_dir)
        external_list = listdir(external_dir)
        for i in internal_list:
            copy(internal_dir+sep+i, external_dir+sep+i)
        for i in external_list:
            if i in internal_list:
                pass
            else:
                copy(external_dir+sep+i, internal_dir+sep+i)
        Print("Synced all replays", color=pink)

    def export(self,selected_replay):
        if selected_replay is None:
            Print("Select a replay", color=red)
            return
        copy(internal_dir+selected_replay, external_dir+selected_replay)
        Print(selected_replay[0:-4]+" exported", top=True, color=pink)

    def importx(self,selected_replay):
        if selected_replay is None:
            Print("Select a replay", color=red)
            return
        copy(external_dir+selected_replay, internal_dir+selected_replay)
        Print(selected_replay[0:-4]+" imported", top=True, color=green)
            
CommonUtils=CommonUtilities()

class MyTabId(Enum):
        INTERNAL = "internal"
        EXTERNAL = "external" 
        SHARE_REPLAYS="share_replay"
             
class Help(PopupWindow):
    def __init__(self):
        uiscale = ba.app.ui.uiscale
        self.width = 1000
        self.height = 300

        PopupWindow.__init__(self,
                             position=(0.0, 0.0),
                             size=(self.width, self.height),
                             scale=1.2,)

        ba.containerwidget(edit=self.root_widget, on_outside_click_call=self.close)
        ba.textwidget(parent=self.root_widget, position=(0, self.height * 0.6),
                      text=f">Replays are exported to\n     {external_dir}\n>Copy replays to the above folder to be able to import them into the game\n>I would live to hear from you,meet me on discord\n                                -LoupGarou(author)")

    def close(self):
        ba.playsound(ba.getsound('swish'))
        ba.containerwidget(edit=self.root_widget, transition="out_right",)


class ShareTabUi(WatchWindow):
    def __init__(self,root_widget=None):        
        self.tab_id = MyTabId.INTERNAL
        self.selected_replay = None      
   
        if root_widget is None:
            self.root = ba.Window(ba.containerwidget(
            size=(900, 670), on_outside_click_call=self.close, transition="in_right")).get_root_widget()
            
        else:   
            self.root=root_widget
            ba.textwidget(parent=self.root,size=(500,500),position=(500,300),text="EEE|EEEEEEEELLELELELELEEKKDK")
              
        self.draw_ui() 
        #ba.containerwidget(edit=self.root, cancel_button=self.close_button)        
               
        
        
    def on_select_text(self, widget, name):       
        existing_widgets = self.scroll2.get_children()
        for i in existing_widgets:
            ba.textwidget(edit=i, color=(1, 1, 1))
        ba.textwidget(edit=widget, color=(1, 1, 0))
        self.selected_replay = name
        
       
  

    def on_tab_select(self, tab_id):
        self.selected_replay=None
        self.tab_id = tab_id
        if tab_id == MyTabId.INTERNAL:
            dir_list = listdir(internal_dir)
            ba.buttonwidget(edit=self.share_button, label="EXPORT", icon=ba.gettexture("upButton"),on_activate_call=self.share) 
        else:
            dir_list = listdir(external_dir)
            ba.buttonwidget(edit=self.share_button, label="IMPORT",
                            icon=ba.gettexture("downButton"),on_activate_call=self.share)
        self.tab_row.update_appearance(tab_id)
        dir_list = sorted(dir_list)
        existing_widgets = self.scroll2.get_children()
        if existing_widgets:
            for i in existing_widgets:
                i.delete()
        height = 900
        # making textwidgets for all replays
        for i in dir_list:
            height -= 40
            a = i
            i = ba.textwidget(
                parent=self.scroll2,
                size=(500, 50),
                text=i.split(".")[0],
                position=(10, height),
                selectable=True,
                max_chars=40,
                corner_scale=1.3,
                click_activate=True,)
            ba.textwidget(edit=i, on_activate_call=ba.Call(self.on_select_text, i, a))
            
    def share(self):
        if self.tab_id == MyTabId.INTERNAL:
            CommonUtils.export(self.selected_replay)
        else:
            CommonUtils.importx(self.selected_replay)
                        
    def draw_ui(self):
        self._height = (
            578
            if uiscale is ba.UIScale.SMALL
            else 670
            if uiscale is ba.UIScale.MEDIUM
            else 800
        )
        self._scroll_height = self._height - 180
        c_height = self._scroll_height - 20
        sub_scroll_height = c_height - 63
        sub_scroll_width = (
                680 if uiscale is ba.UIScale.SMALL else 640
            )
        v = c_height - 30
        v -= sub_scroll_height + 23   
        smlh = 190 if uiscale is ba.UIScale.SMALL else 225    
           
        scroll = ba.scrollwidget(
                parent=self.root,
                position=(smlh, v),
                size=(sub_scroll_width, sub_scroll_height),
            )   
        
        self.scroll2 = ba.columnwidget(parent=scroll, size=(
            500, 900))

       # self.close_button = ba.buttonwidget(
#            parent=self.root,
#            position=(90, 560),
#            button_type='backSmall',
#            size=(60, 60),
#            label=ba.charstr(ba.SpecialChar.BACK),
#            scale=1.5,
#            on_activate_call=self.close)

        ba.textwidget(
            parent=self.root,
            size=(200, 100),
            position=(350, 550),
            scale=2,
            selectable=False,
            h_align="center",
            v_align="center",
            text=title,
            color=green)

        ba.buttonwidget(
            parent=self.root,
            position=(650, 580),
            size=(35, 35),
            texture=ba.gettexture("achievementEmpty"),
            label="",
            on_activate_call=Help)

        tabdefs = [(MyTabId.INTERNAL, 'INTERNAL'), (MyTabId.EXTERNAL, "EXTERNAL")]
        self.tab_row = TabRow(self.root, tabdefs, pos=(150, 500-5),
                              size=(500, 300), on_select_call=self.on_tab_select)
                              
        b_width = 90 if uiscale is ba.UIScale.SMALL else 178
        b_height = (
                80
                if uiscale is ba.UIScale.SMALL
                else 142
                if uiscale is ba.UIScale.MEDIUM
                else 190
            )
        
        btnh = 40 if uiscale is ba.UIScale.SMALL else 40
        btnv = (
                c_height
                - (
                    48
                    if uiscale is ba.UIScale.SMALL
                    else 45
                    if uiscale is ba.UIScale.MEDIUM
                    else 40
                )
                - b_height
            )
        
        
        b_space_extra = (
                40
                if uiscale is ba.UIScale.SMALL
                else -2
                if uiscale is ba.UIScale.MEDIUM
                else -5
            )
        btnv -= b_height + b_space_extra
        
        self.share_button = ba.buttonwidget(
            parent=self.root,
            size=(b_width, b_height),
            position=(btnh, btnv),
            scale=1.5,
            button_type="square",
            label="EXPORT",
            text_scale=2,
            icon=ba.gettexture("upButton"),
            on_activate_call=ba.Call(CommonUtils.export,self.selected_replay))

        btnv -=b_height + b_space_extra
        
        sync_button = ba.buttonwidget(
            parent=self.root,
            size=(b_width, b_height),
            position=(btnh, btnv),
            scale=1.5,
            button_type="square",
            label="SYNC",
            text_scale=2,
            icon=ba.gettexture("ouyaYButton"),
            on_activate_call=CommonUtils.sync_confirmation)
        
        self.on_tab_select(MyTabId.INTERNAL)             
            
    def close(self):
        ba.playsound(ba.getsound('swish'))
        ba.containerwidget(edit=self.root, transition="out_right",)    
    


# ++++++++++++++++for keyboard navigation++++++++++++++++

        #ba.widget(edit=self.enable_button, up_widget=decrease_button, down_widget=self.lower_text,left_widget=save_button, right_widget=save_button)

# ----------------------------------------------------------------------------------------------------
                
class ShareTab(WatchWindow):
    
                        
    @override(WatchWindow)
    def __init__(self,
        transition: str | None = 'in_right',
        origin_widget: ba.Widget | None = None,
        oldmethod=None):           
        self.my_tab_container=None             
        self._old___init__(transition,origin_widget)     
        
        
        self._tab_row.tabs[self.TabID.MY_REPLAYS].button.delete()#deleting old tab button
        
        tabdefs = [(self.TabID.MY_REPLAYS,
                ba.Lstr(resource=self._r + '.myReplaysText'),),
            (MyTabId.SHARE_REPLAYS,"Share Replays"),]
        
        uiscale = ba.app.ui.uiscale
        x_inset = 100 if uiscale is ba.UIScale.SMALL else 0
        tab_buffer_h = 750 + 2 * x_inset
        self._tab_row = TabRow(
            self._root_widget,
            tabdefs,
            pos=((tab_buffer_h /1.5)* 0.5, self._height - 130),
            size=((self._width - tab_buffer_h)*2, 50),
            on_select_call=self._set_tab)
        
        self._tab_row.update_appearance(self.TabID.MY_REPLAYS)
        
    @override(WatchWindow)
    def _set_tab(self, tab_id,oldfunc=None):
        self._old__set_tab(tab_id)        
        if self.my_tab_container:
                self.my_tab_container.delete()     
        if tab_id == MyTabId.SHARE_REPLAYS:
            
            
            scroll_left = (self._width - self._scroll_width) * 0.5
            scroll_bottom = self._height - self._scroll_height - 79 - 48
         
            c_width = self._scroll_width
            c_height = self._scroll_height - 20
            sub_scroll_height = c_height - 63
            self._my_replays_scroll_width = sub_scroll_width = (
                680 if uiscale is ba.UIScale.SMALL else 640
            )

            self.my_tab_container = ba.containerwidget(
                parent=self._root_widget,
                position=(scroll_left,
                    scroll_bottom + (self._scroll_height - c_height) * 0.5,),
                size=(c_width, c_height),
                background=False,
                selection_loops_to_parent=True,
            ) 
           
            ShareTabUi(self.my_tab_container)
            
    
# ba_meta export plugin

class Loup(ba.Plugin):
    def on_app_running(self):
      WatchWindow.__init__ = ShareTab.__init__
 
    def has_settings_ui(self):
        return True

    def show_settings_ui(self, button):
        ShareTabUi()

