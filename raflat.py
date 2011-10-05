# -*- coding: utf-8 -*-
import datetime
import logging
import re

from google.appengine.api import urlfetch
from google.appengine.ext import db


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
        return u'%s (%s) from %s till %s' \
               % (self.name, price, self.start, self.end)

class Ruokasali(BaseRafla):

    @classmethod
    def scrape_menu(cls):
        rs = urlfetch.fetch('http://ruokasali.fi/lounas.html')
        assert rs.status_code == 200
        menu, = re.search(r'<h1><br /><br />Lounaslista(.*)<strong>TERVETULOA!', rs.content.decode('utf-8')).groups()
        servings = reduce(lambda ss, d: ss + cls._scrape_servings(d),
                          re.split(r'<strong>\w+ (?=\d+\.\d+)', menu)[1:],
                          [])
        return servings

    @classmethod
    def _scrape_servings(cls, menu):
        d, m, basic, dessert, value = \
            re.match(r'(\d+)\.(\d+).+?<p>(.+)J.lkiruoka(.*)Grillist.(.+)', menu).groups()
        start = datetime.datetime(2011, int(m), int(d), 10, 30)
        end = datetime.datetime(2011, int(m), int(d), 14, 00)
        servings = [Serving(name=name, price=[900], start=start, end=end)
                    for name in map(unicode.strip, re.split(r' *<.+?> *', basic))
                    if name]
        servings += [Serving(name=name, price=[], start=start, end=end, food_type=['dessert'])
                    for name in map(unicode.strip, re.split(r' *<.+?> *', dessert))
                    if name]
        servings += [Serving(name=name, price=[920, 1380], start=start, end=end)
                    for name in map(unicode.strip, re.split(r' *<.+?> *', value))
                    if name]
        return servings
