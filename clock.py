#!/usr/bin/env python
import math
import datetime

def hsl_to_rgb(h, s, l):
    if s == 0:
        r = g = b = l
    else:
        def hue2rgb(p, q, t):
            if t < 0: t += 1
            if t > 1: t -= 1
            if t < 1/6: return p + (q - p) * 6 * t
            if t < 1/2: return q
            if t < 2/3: return p + (q - p) * 6 * (2/3 - t)
            return p

        q = l * (1 + s) if l < 0.5 else l + s - l*s
        p = 2*l - q
        r = hue2rgb(p, q, h + 1/3)
        g = hue2rgb(p, q, h)
        b = hue2rgb(p, q, h - 1/3)
    return tuple(round(x*255) for x in (r,g,b))


class FParam:
    def __init__(self, k, n):
        self.k = k
        self.n = n

_fparams = [
          FParam(18.0, 0.035)
        , FParam(14.0, 0.07)
        ]

class SParam:
    def __init__(self, k, o):
        self.k = k
        self.o = o

_sparams = [
          SParam( 0.0, -1.0)
        , SParam(-1.0,  1.0)
        , SParam(-2.0,  3.0)
        , SParam(-3.0,  5.0)
        ]

def sigmoid(t, i, fp=_fparams[1]):
    sk = -i
    so = -1.0 + 2*i
    return (1.0/3.0 + fp.n) / (1.0 + math.exp(-fp.k * (t + sk/3.0))) + so/6.0 - fp.n/2.0

def time_to_hue(t, fp=_fparams[1]):
    return sigmoid(t, round(t*3.0), fp)

def time_to_color(t):
    return "#{:02x}{:02x}{:02x}".format(*hsl_to_rgb(time_to_hue(t),1,0.125))

def get_time():
    time = datetime.datetime.now()
    t = (3600*time.hour + 60*time.minute + time.second + 1e-6*time.microsecond)/(24*60*60)
    t = 1.0 - ((t*8) % 1)
    c = time_to_color(t)
    return (c, time.strftime("%a %Y-%m-%d %H:%M:%S"))

if __name__ == '__main__':
    c, s = get_time()
    print('^fg(#9e9e9e)^bg({})'.format(c))
