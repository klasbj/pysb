#!/usr/bin/env python

import sys
import signal
import select
from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSocketNotifier, QObject, QPointF
from PyQt5.QtGui import QPainter, QColor, QFont, QPolygonF, QImage
from PyQt5.QtNetwork import QLocalServer

import clock


IMAGE_CACHE = dict()
def get_image(path):
    if not path in IMAGE_CACHE:
        i = QImage(path)
        i.setColor(1, QColor(0,0,0,0).rgba())
        i.setColor(2, QColor('#9e9e9e').rgba())
        if i.colorCount() > 2:
            i.setColor(3, QColor('#3d3dff').rgba())
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

        


class BarPainter(QPainter):
    def __init__(self, *args):
        super().__init__(*args)

    def draw_hlsection(self,x,y,w,h,left=True,color='#262626'):
        """Draw the divider and bg for a section."""
        self.save()
        self.setPen(Qt.NoPen)
        self.setBrush(QColor(color))
        if w > 0:
            w += 16
        if left:
            polygon = [QPointF(x,y)]
            polygon.append(QPointF(x+9,y+(h)/2.0))
            polygon.append(QPointF(x,y+h))
            polygon.append(QPointF(x+9+w,y+h))
            polygon.append(QPointF(x+9+w+9,y+(h)/2.0))
            polygon.append(QPointF(x+9+w,y))
        else:
            polygon = [QPointF(x,y+(h-1)/2.0)]
            polygon.append(QPointF(x+9,y+h))
            polygon.append(QPointF(x+9+w+9,y+h))
            polygon.append(QPointF(x+9+w,y+(h)/2.0))
            polygon.append(QPointF(x+9+w+9,y))
            polygon.append(QPointF(x+9,y))
        self.drawPolygon(QPolygonF(polygon))
        self.restore()
        return (x+9+8, x + 9 + w + 9)


class Bar(QWidget):
    TOP = 1
    BOTTOM = 2

    def __init__(self, x, y, w, h, **kwargs):
        QWidget.__init__(self, **kwargs)
        self.move(x,y)
        self.resize(w, h)
        self.text = None

    def setText(self, text):
        self.text = text
        self.update()

    def paintEvent(self, event):
        painter = BarPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor('#1c1c1c'))
        #painter.setBrush(QColor('black'))
        painter.drawRect(self.rect())

        painter.setFont(QFont('deja vu sans mono for powerline', 11))
        painter.setPen(QColor('#9e9e9e'))

        def paint_dwm(painter, x, y, h, text):
            fm = painter.fontMetrics();
            wss, layout, title = text.split('|')
            xorig = x
            x += 2
            for ws in wss.split(' '):
                painter.save()
                painter.setPen(QColor('#9e9e9e'))
                if ws[0] == '^':
                    painter.setPen(QColor('#3d3dff'))
                    if ws[1] == '!':
                        s = ws[2:]
                        painter.fillRect(x+1, y, fm.width(s)-2, y+1, QColor('#ff7e3d'))
                    else:
                        s = ws[1:]
                    #painter.fillRect(x-2, y, fm.width(s) + 4, y+2, QColor('#000000'))
                elif ws[0] == '!':
                    #painter.setPen(QColor('#ff7e3d'))
                    s = ws[1:]
                    painter.fillRect(x+1, y, fm.width(s)-2, y+1, QColor('#ff7e3d'))
                elif ws[0] == '$':
                    #painter.setPen(QColor('#9e9e9e'))
                    s = ws[1:]
                else:
                    s = ws
                    painter.setPen(QColor('#4e4e4e'))

                painter.drawText(x, y, fm.width(s), h, Qt.AlignLeft | Qt.AlignVCenter, s)
                x += fm.width(s) + 4
                painter.restore()

            lw = fm.width(layout)
            tx, x = painter.draw_hlsection(x+4, y, lw, h)
            painter.drawText(tx, y, lw, h, Qt.AlignLeft | Qt.AlignVCenter, layout)

            painter.drawText(x+8, y, fm.width(title), h, Qt.AlignLeft | Qt.AlignVCenter, title)

        def paint_clock(painter, x, y, h):
            fm = painter.fontMetrics();
            color, timestr = clock.get_time()
            cw = fm.width(timestr)
            x -= 2
            x -= cw
            painter.fillRect(x - 13, y, 16 + cw + 2, h, QColor(color))
            painter.drawText(x, y, cw, h, Qt.AlignRight | Qt.AlignVCenter, timestr)
            x -= 4
            return x

        if self.text:
            paint_dwm(painter, 0, 0, self.rect().height(), self.text)

        rx = paint_clock(painter, self.rect().right(), 0, self.rect().height())

        def parse_string(s="ksjdnf ^i(/home/klasse/wm/statusbars/images/snd-2.xpm) ^i(/home/klasse/wm/statusbars/images/snd-m.xpm) skjadf sd"):
            def sgen(s):
                for c in s:
                    yield c
            tokens = []
            tok = ''
            sg = sgen(s)
            for c in sg:
                if c == '^':
                    tokens.append(tok)
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
                        tokens.append(get_image(path))
                    else:
                        tokens.append((cmd,args))
                else:
                    tok += c
            tokens.append(tok)
            return tokens

        def calculate_width(painter, tokens):
            fm = painter.fontMetrics();
            w = 0
            for tok in tokens:
                if isinstance(tok, str):
                    w += fm.width(tok)
                elif isinstance(tok, QImage):
                    w += tok.width()
            return w

        def paint_tokens(painter, tokens, x, y, h):
            fm = painter.fontMetrics();
            for tok in tokens:
                if isinstance(tok, str):
                    painter.drawText(x, y, fm.width(tok), h, Qt.AlignLeft | Qt.AlignVCenter, tok)
                    x += fm.width(tok)
                elif isinstance(tok, QImage):
                    painter.drawImage(x, h/2.0 - tok.height()/2.0, tok)
                    x += tok.width()


        tokens = parse_string()
        w = calculate_width(painter, tokens)
        rx -= 18 + w + 16
        tx, _ = painter.draw_hlsection(rx, 0, w, self.rect().height(), left=False)
        paint_tokens(painter, tokens, tx, 0, self.rect().height())






def main():
    app = QApplication(sys.argv)

    io = InputHandler()

    # Set up signal handler to manage Ctrl+c
    signal.signal(signal.SIGINT, lambda *_: QApplication.quit())
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None) # let python run every 500ms

    desktop = app.desktop()
    sgeom = desktop.screenGeometry()

    w = Bar(sgeom.left(), sgeom.top(), sgeom.width(), 18, flags=Qt.Widget | Qt.BypassWindowManagerHint)
    w.setWindowTitle("bu")
    w.show()
    #w.lower()
    
    timer.timeout.connect(w.update) # let python run every 500ms
    io.line.connect(w.setText)

    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
