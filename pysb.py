#!/usr/bin/env python

import os
import re
import sys
import signal
import select
from enum import IntEnum, unique
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSocketNotifier, QObject, QPointF, QLineF
from PyQt5.QtGui import QPainter, QColor, QFont, QPolygonF, QImage, QPainterPath
from PyQt5.QtNetwork import QLocalServer

import clock

# settings
FONT_SIZE_PT = 8
FONT = QFont('deja vu sans mono for powerline', FONT_SIZE_PT)
ARROW_WIDTH = 8 # fontMetrics().width(' ') somehow?
BAR_HEIGHT = 15

NORMAL_FG_COLOR = "#9e9e9e"
LOW_FG_COLOR = "#4e4e4e"



timer = None
bars = []

@unique
class Dock(IntEnum):
    top = 0
    bottom = 1
    def parse(s):
        s = s.lower()
        if s in Dock.__members__:
            return Dock.__members__[s]
        else:
            raise "Enum value '{}' does not exist.".format(s)

class Float(IntEnum):
    left = 0
    left_hl = 1
    center_l = 2
    center = 2 # alias to support old behavior
    right = 3
    right_hl = 4
    center_r = 5

    def parse(s):
        s = s.lower()
        if s in Float.__members__:
            return Float.__members__[s]
        else:
            raise "Enum value '{}' does not exist.".format(s)

class Token:
    def __init__(self):
        pass
    def width(self, painter):
        pass
    def render(self, painter, x, y, h):
        pass

class StringToken(Token):
    def __init__(self, s):
        super().__init__()
        self.s = s
    def width(self, painter):
        return painter.fontMetrics().width(self.s)
    def render(self, painter, x, y, h):
        painter.drawText(x, y, painter.fontMetrics().width(self.s), h,
                         Qt.AlignLeft | Qt.AlignVCenter, self.s)

gaps = { "#" : 4, "|" : 8 }
class GapToken(Token):
    def __init__(self, s):
        self.gap = gaps[s]
    def width(self, painter):
        return self.gap

class ImageToken(Token):
    def __init__(self, img_path):
        self.img = get_image(img_path)
    def width(self, painter):
        return self.img.width()
    def render(self, painter, x, y, h):
        painter.drawImage(x, h/2.0 - self.img.height()/2.0, self.img)

class FgChangeToken(Token):
    def __init__(self, fg):
        self.fg_color = QColor(fg)
    def width(self, painter):
        return 0
    def render(self, painter, x, y, h):
        painter.setPen(self.fg_color)

class Area(QObject):

    changed = pyqtSignal()

    def __init__(self, floatd, weight):
        super().__init__()
        self.data = ''
        self.floatd = floatd
        if floatd <= Float.center_l:
            self.weight = -weight
        else:
            self.weight = weight

    def render(self, painter, x, y, h):
        painter.save()
        for tok in self.data:
            tok.render(painter, x, y, h)
            x += tok.width(painter)
        painter.restore()

    def width(self, painter):
        return sum(tok.width(painter) for tok in self.data)

    def set_text(self, text):
        def sgen(s):
            for c in s:
                yield c
        tokens = []
        tok = ''
        sg = sgen(text)
        for c in sg:
            if c == '^':
                tokens.append(StringToken(tok))
                tok = ''
                cmd = ''
                for cc in sg:
                    if cc == '(':
                        break
                    cmd += cc
                args = ''
                for cc in sg:
                    if cc == ')':
                        break
                    args += cc
                if cmd == 'i':
                    path = args.split(',')[0]
                    tokens.append(ImageToken(path))
                elif cmd == 'low':
                    tokens.append(FgChangeToken(LOW_FG_COLOR))
                elif cmd == 'norm':
                    tokens.append(FgChangeToken(NORMAL_FG_COLOR))
                else:
                    pass
                    #tokens.append((cmd,args))
            elif c in "|#":
                tokens.append(StringToken(tok))
                tok = ''
                tokens.append(GapToken(c))
            else:
                tok += c
        tokens.append(StringToken(tok))
        if tokens != self.data:
            self.data = tokens
            self.changed.emit()

bindir = os.path.dirname(os.path.realpath(__file__))

class DwmLtArea(Area):
    def __init__(self, floatd, weight):
        super().__init__(floatd,weight)
        self.imgs = [
                  (re.compile(r'\[\]='), get_image(os.path.join(bindir, 'tiled.xpm')))
                , (re.compile(r'\[.*\]'), get_image(os.path.join(bindir, 'maximized.xpm')))
                , (re.compile(r'><>'), get_image(os.path.join(bindir, 'floating.xpm')))
                ]
        self.data = self.imgs[0]

    def set_text(self, text):
        for r, i in self.imgs:
            if r.match(text):
                self.data = i
                self.changed.emit()
                break

    def width(self, painter):
        return self.data.width()

    def render(self, painter, x, y, h):
        painter.drawImage(x, h/2.0 - self.data.height()/2.0, self.data)

class DwmWsArea(Area):
    def __init__(self, floatd, weight):
        super().__init__(floatd,weight)
        self.data = []

    def set_text(self, text):
        self.data = []
        for ws in text.split(' '):
            m = re.match(r'(?P<mod>[!^$]+)?(?P<name>\S+)', ws)
            self.data.append((m.group('name'),m.group('mod')))
        self.changed.emit()

    def width(self, painter):
        fm = painter.fontMetrics();
        return sum(fm.width(x[0]) for x in self.data) + 8*max(0,len(self.data)-1)

    def render(self, painter, x, y, h):
        fm = painter.fontMetrics();
        for ws in self.data:
            s, mod = ws
            painter.save()
            painter.setPen(QColor(NORMAL_FG_COLOR))
            if mod is None:
                painter.setPen(QColor(LOW_FG_COLOR))
            else:
                if '^' in mod:
                    painter.setPen(QColor('#3d3dff'))
                if '!' in mod:
                    painter.fillRect(x+1, y, fm.width(s)-2, y+1, QColor('#ff7e3d'))

            painter.drawText(x, y, fm.width(s), h, Qt.AlignLeft | Qt.AlignVCenter, s)
            x += fm.width(s) + 8
            painter.restore()

        #lw = fm.width(layout)
        #tx, x = painter.draw_hlsection(x+4, y, lw, h)
        #painter.drawText(tx, y, lw, h, Qt.AlignLeft | Qt.AlignVCenter, layout)

        #painter.drawText(x+8, y, fm.width(title), h, Qt.AlignLeft | Qt.AlignVCenter, title)

class ClockArea(Area):
    def __init__(self, floatd, weight):
        super().__init__(floatd,weight)
        if timer != None:
            timer.timeout.connect(self.tick)
        self.tick()

    def set_text(self, _):
        raise "Can't set text of ClockArea"

    def tick(self):
        data = clock.get_time()
        if data != self.data:
            self.data = data
            self.changed.emit()

    def width(self, painter):
        fm = painter.fontMetrics()
        return fm.width(self.data[1])

    def render(self, painter, x, y, h):
        # we will receive x for the left-most part of the clock
        fm = painter.fontMetrics()
        color, timestr = self.data
        cw = fm.width(timestr)
        #x += 4
        bx = x
        bw = cw
        if self.floatd <= Float.center_l:
            bx -= 2
            bw += ARROW_WIDTH + 4 + 2
            assert(bx == 0)
        else:
            bx -= ARROW_WIDTH + 4
            bw += ARROW_WIDTH + 4 + 2

        painter.fillRect(bx, y, bw, h, QColor(color))
        painter.drawText(x, y, cw, h, Qt.AlignRight | Qt.AlignVCenter, timestr)

IMAGE_CACHE = dict()
def get_image(path):
    if not path in IMAGE_CACHE:
        i = QImage(path)
        #i.setColor(1, QColor(0,0,0,0).rgba())
        #i.setColor(2, QColor('#9e9e9e').rgba())
        #if i.colorCount() > 2:
        #    i.setColor(3, QColor('#3d3dff').rgba())
        IMAGE_CACHE[path] = i
    return IMAGE_CACHE[path]

class InputHandler(QObject):

    line = pyqtSignal(str)
    cnt = 0

    def __init__(self):
        super(InputHandler, self).__init__()
        self.sockets = {sys.stdin.fileno() : [sys.stdin]}
        self.notifiers = []
        for s in self.sockets.keys():
            n = QSocketNotifier(s, QSocketNotifier.Read)
            n.activated.connect(self.activated)
            self.sockets[s].append(n)

    def activated(self, fd):
        s = self.sockets[fd][0]
        line = s.readline()
        InputHandler.cnt += 1
        if len(line) == 0:
            # at eof
            self.sockets[fd][1].setEnabled(False)
        else:
            self.line.emit(line.rstrip('\n'))

area_map = {}
def handle_input(line):
    #print("handle line '{}'".format(line), file=sys.stderr)
    cmd, args = line.split(' ', maxsplit=1)
    if cmd == 'text':
        area, text = args.split(' ', maxsplit=1)
        if area in area_map:
            area_map[area].set_text(text)
        else:
            print('Unknown area:', area, file=sys.stderr)
    elif cmd == 'add_area':
        # add_area id screen TOP|BOTTOM weight LEFT|RIGHT|CENTER [type]
        args = args.split(' ')
        id_, screen, dock, weight, floatd = args[:5]
        screen = int(screen)
        try:
            dock = Dock.parse(dock)
        except str as e:
            dock = Dock.top
            print(e, file=sys.stderr)
        weight = int(weight)
        try:
            floatd = Float.parse(floatd)
        except str as e:
            floatd = Float.center_r
            print(e, file=sys.stderr)
        t = Area
        if len(args) > 5:
            # last argument is type
            if args[5] == 'clock':
                t = ClockArea
            elif args[5] == 'dwm-ws':
                t = DwmWsArea
            elif args[5] == 'dwm-lt':
                t = DwmLtArea
        a = t(floatd, weight)
        area_map[id_] = a
        if screen > len(bars):
            print("ignoring area '{}', unknown screen '{}'.".format(id_, screen), file=sys.stderr)
        bars[screen][dock].add_area(a)
    elif cmd == 'rm_area':
        pass
    elif cmd == 'screen':
        pass

class BarPainter(QPainter):
    def __init__(self, *args):
        super().__init__(*args)

    def draw_hlsection(self,x,y,w,h,floatd=Float.left,color='#262626'):
        """Draw the divider and bg for a section."""
        self.save()
        self.setPen(Qt.NoPen)
        self.setBrush(QColor(color))
        if w > 0:
            w += 16
        if floatd <= Float.center_l:
            polygon = [QPointF(x,y)]
            polygon.append(QPointF(x+ARROW_WIDTH,y+(h)/2.0))
            polygon.append(QPointF(x,y+h))
            polygon.append(QPointF(x+ARROW_WIDTH+w,y+h))
            polygon.append(QPointF(x+ARROW_WIDTH+w+ARROW_WIDTH,y+(h)/2.0))
            polygon.append(QPointF(x+ARROW_WIDTH+w,y))
        else:
            polygon = [QPointF(x,y+(h-1)/2.0)]
            polygon.append(QPointF(x+ARROW_WIDTH,y+h))
            polygon.append(QPointF(x+ARROW_WIDTH+w+ARROW_WIDTH,y+h))
            polygon.append(QPointF(x+ARROW_WIDTH+w,y+(h)/2.0))
            polygon.append(QPointF(x+ARROW_WIDTH+w+ARROW_WIDTH,y))
            polygon.append(QPointF(x+ARROW_WIDTH,y))
        self.drawPolygon(QPolygonF(polygon))
        self.restore()
        return (x+ARROW_WIDTH+8, x + ARROW_WIDTH + w + ARROW_WIDTH)


class Bar(QWidget):
    TOP = 1
    BOTTOM = 2

    def __init__(self, x, y, w, h, **kwargs):
        QWidget.__init__(self, **kwargs)
        self.move(x,y)
        self.resize(w, h)
        self.text = None
        self.areas = []

    def add_area(self, area):
        self.areas.append(area)
        area.changed.connect(self.update)

    def setText(self, text):
        self.text = text
        self.update()

    def paintEvent(self, event):
        painter = BarPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#1c1c1c'))
        #painter.setBrush(QColor('black'))
        painter.drawRect(self.rect())

        painter.setFont(FONT)
        #print(painter.fontMetrics().width(' '), 'x', painter.fontMetrics().height())
        painter.setPen(QColor(NORMAL_FG_COLOR))

        drect = self.rect()
        lx = drect.left()
        rx = drect.right()
        y = drect.top()
        h = drect.height()

        for sa in (Float.left, Float.left_hl, Float.center_l):
            areas = [a for a in self.areas if a.floatd == sa and a.width(painter) > 0]
            tw = sum(a.width(painter) for a in areas) + max(0,len(areas)-1)*(ARROW_WIDTH+16)
            sx = lx + (4 if sa > Float.left else 2)
            if sa == Float.left_hl:
                sx, lx = painter.draw_hlsection(sx, y, tw, h, sa)
            first = True
            for a in sorted(areas, key=lambda x: x.weight):
                if not first:
                    sx += 8
                    painter.save()
                    #painter.setPen(QColor('#1c1c1c' if sa == Area.FLOAT_LEFT_HL else '#262626'))
                    painter.setBrush(Qt.NoBrush)
                    p = QPainterPath()
                    p.moveTo(sx, y)
                    p.lineTo(sx+ARROW_WIDTH-0.5, y+h/2)
                    p.lineTo(sx, y+h)
                    painter.drawPath(p)
                    painter.restore()

                    sx += ARROW_WIDTH + 8
                first = False
                a.render(painter, sx, y, h)
                sx += a.width(painter)
            if sa != Float.left_hl:
                lx = sx

        for sa in (Float.right, Float.right_hl, Float.center_r):
            areas = [a for a in self.areas if a.floatd == sa]
            tw = sum(a.width(painter) for a in areas) + max(0,len(areas)-1)*(ARROW_WIDTH+16)
            sx = rx = rx - tw - (4 if sa > Float.right else 0)
            if sa == Float.right_hl:
                rx -= 2*ARROW_WIDTH+(16 if tw > 0 else 0)
                sx, _ = painter.draw_hlsection(rx, y, tw, h, sa)
            first = True
            for a in sorted(areas, key=lambda x: x.weight):
                if not first:
                    painter.save()
                    #painter.setPen(QColor('#1c1c1c' if sa == Area.FLOAT_LEFT_HL else '#262626'))
                    painter.setBrush(Qt.NoBrush)
                    p = QPainterPath()
                    p.moveTo(sx+ARROW_WIDTH-0.5, y)
                    p.lineTo(sx, y+h/2.0)
                    p.lineTo(sx+ARROW_WIDTH-0.5, y+h)
                    painter.drawPath(p)
                    painter.restore()

                    sx += ARROW_WIDTH + 8
                first = False
                a.render(painter, sx, y, h)
                sx += a.width(painter) + 8


        #if self.text:
        #    da = DwmArea()
        #    da.set_text(self.text)
        #    da.render(painter, 0, 0, self.rect().height())

        #rx = paint_clock(painter, self.rect().right(), 0, self.rect().height())

        #s = "ksjdnf ^i(/home/klasse/wm/statusbars/images/snd-2.xpm) ^i(/home/klasse/wm/statusbars/images/snd-m.xpm) skjadf sd"
        #a = Area(floatd=Area.FLOAT_RIGHT, weight=100)
        #a.set_text(s)

        #w = a.width(painter)
        #rx -= 18 + w + 16
        #tx, _ = painter.draw_hlsection(rx, 0, w, self.rect().height(), floatd=a.floatd)
        #a.render(painter, tx, 0, self.rect().height())






def main():
    app = QApplication(sys.argv)

    io = InputHandler()

    # Set up signal handler to manage Ctrl+c
    signal.signal(signal.SIGINT, lambda *_: QApplication.quit())
    global timer
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None) # let python run every 500ms

    desktop = app.desktop()
    sgeom = desktop.screenGeometry()

    global bars
    bars.append(dict())
    bars[0][Dock.top] = Bar(sgeom.left(), sgeom.top(), sgeom.width(), BAR_HEIGHT, flags=Qt.Widget | Qt.BypassWindowManagerHint)
    bars[0][Dock.bottom] = Bar(sgeom.left(), sgeom.bottom()-BAR_HEIGHT+1, sgeom.width(), BAR_HEIGHT, flags=Qt.Widget | Qt.BypassWindowManagerHint)

    print(bars, file=sys.stderr)

    for bar in bars[0].values():
        bar.show()
        #bar.lower()

    io.line.connect(handle_input)

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
