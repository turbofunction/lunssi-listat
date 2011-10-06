# -*- coding: utf-8 -*-
import datetime
import logging
import re

from google.appengine.api import urlfetch
from google.appengine.ext import db


def decode_content(response):
    content = response.content
    if not content:
        return
    encoding = re.search('charset=(.+)$', response.headers.get('content-type', ''))
    if encoding:
        return content.decode(encoding.group(1))
    return content

def maybe(default, fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except AssertionError:
        return default

def some(itr):
    for s in itr:
        if s:
            yield s

def spliz(pattern, string):
    return some(map(unicode.strip, re.split(pattern, string)))

def match(pattern, string):
    return re.match(pattern, string, re.I | re.U)

def search(pattern, string):
    return re.search(pattern, string, re.I | re.U)

class BaseRafla(object):
    pass

class Serving(db.Model):
    name = db.StringProperty()
    food_type = db.StringListProperty()
    price = db.ListProperty(int)
    start = db.DateTimeProperty()
    end = db.DateTimeProperty()

    def __unicode__(self):
        if self.price[1:]:
            price = '%.2f€-%.2f€' % (self.price[0] / 100., self.price[-1] / 100.)
        elif self.price[0:]:
            price = '%.2f€' % (self.price[0] / 100.)
        else:
            price = '-'
        return u'%s [%s] (%s) from %s till %s' \
               % (self.name, ', '.join(self.food_type), price, self.start, self.end)

class Ruokasali(BaseRafla):
    @classmethod
    def scrape_menu(cls):
        rs = urlfetch.fetch('http://ruokasali.fi/lounas.html')
        assert rs.status_code == 200
        menu, = search(ur'<h1><br /><br />Lounaslista(.*)<strong>TERVETULOA!', decode_content(rs)).groups()
        servings = reduce(lambda ss, d: ss + maybe([], cls._scrape_servings, d),
                          spliz(r'<strong>\w+ (?=\d+\.\d+)', menu),
                          [])
        return servings

    @classmethod
    def _scrape_servings(cls, menu):
        day_menu = match(ur'(\d+)\.(\d+).+?<p>(.+)Jälkiruoka(.*)Grillistä(.+)', menu)
        assert day_menu
        d, m, basic, dessert, value = day_menu.groups()
        start = datetime.datetime(2011, int(m), int(d), 10, 30)
        end = datetime.datetime(2011, int(m), int(d), 14, 00)
        servings = [Serving(name=name, price=[900], start=start, end=end)
                    for name in spliz(r'<.+?>', basic)]
        servings += [Serving(name=name, price=[], start=start, end=end, food_type=['dessert'])
                    for name in spliz(r'<.+?>', dessert)]
        servings += [Serving(name=name, price=[920, 1380], start=start, end=end)
                    for name in spliz(r'<.+?>', value)]
        return servings
