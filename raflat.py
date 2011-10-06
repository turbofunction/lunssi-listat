# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import logging
import re

from google.appengine.api import urlfetch
from google.appengine.ext import db

from django.conf import settings


def decode_content(response):
    if settings.DEBUG:
        logging.debug("response headers: %r" % response.headers)
    content = response.content
    if not content:
        return
    encoding = re.search(r"charset=(.+)$", response.headers.get('content-type', ''))
    if encoding:
        return content.decode(encoding.group(1))
    else:
        return content.decode('utf-8')

def maybe(default, fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except AssertionError, e:
        if settings.DEBUG:
            logging.debug(e, exc_info=1)
            logging.debug("Exception from %s(*%r, **%r)" % (fn.__name__, args, kw))
        return default
    except ValueError, e:
        if any(e.message.startswith(m)
               for m in ("need more than",
                         "too many values to unpack")):
            if settings.DEBUG:
                logging.debug(e, exc_info=1)
                logging.debug("Exception from %s(*%r, **%r)" % (fn.__name__, args, kw))
            return default
        raise
    except AttributeError, e:
        if any(e.message.startswith(m)
               for m in ("'NoneType' object has no attribute 'groups'",)):
            if settings.DEBUG:
                logging.debug(e, exc_info=1)
                logging.debug("Exception from %s(*%r, **%r)" % (fn.__name__, args, kw))
            return default
        raise

def some(itr):
    for s in itr:
        if s:
            yield s

def spliz(pattern, string):
    return some(map(unicode.strip, re.split(pattern, string)))

def match(pattern, string):
    return re.match(pattern, string, re.I | re.U | re.S)

def search(pattern, string):
    return re.search(pattern, string, re.I | re.U | re.S)


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
        return u"%s [%s] (%s) from %s till %s" \
               % (self.name, ', '.join(self.food_type), price, self.start, self.end)


class Ruokasali(BaseRafla):
    @classmethod
    def scrape_menu(cls):
        rs = urlfetch.fetch("http://ruokasali.fi/lounas.html")
        assert rs.status_code == 200
        starth, startm, endh, endm, menu = \
            search(ur"Lounaslista.*?klo (\d+).(\d+).+?(\d+).(\d+)(.*)<strong>TERVETULOA!",
                   decode_content(rs))\
                .groups()
        starting = timedelta(hours=int(starth), minutes=int(startm))
        ending = timedelta(hours=int(endh), minutes=int(endm))
        servings = reduce(lambda ss, d: ss + maybe([], cls._scrape_servings, d, starting, ending),
                          spliz(r"<strong>\w+ (?=\d+\.\d+)", menu),
                          [])
        return servings

    @classmethod
    def _scrape_servings(cls, menu, starting, ending):
        d, m, basic, dessert, value = \
            match(ur"(\d+)\.(\d+).+?<p>(.+)Jälkiruoka(.*)Grillistä(.+)", menu).groups()
        start = datetime(2011, int(m), int(d)) + starting
        end = datetime(2011, int(m), int(d)) + ending
        servings = [Serving(name=name, price=[900], start=start, end=end)
                    for name in spliz(r"<.+?>", basic)]
        servings += [Serving(name=name, price=[], start=start, end=end, food_type=['dessert'])
                    for name in spliz(r"<.+?>", dessert)]
        servings += [Serving(name=name, price=[920, 1380], start=start, end=end)
                    for name in spliz(r"<.+?>", value)]
        return servings


class Rivoletto(BaseRafla):
    @classmethod
    def scrape_menu(cls):
        rs = urlfetch.fetch('http://www.rivolirestaurants.fi/rivoletto/lounas_txt.html')
        assert rs.status_code == 200
        starth, endh, da, mo, menu = \
            search(ur"arkisin klo (\d+)-(\d+).*?LOUNAS .*? (\d+)\.(\d+)(.*)Albertinkatu", decode_content(rs)).groups()
        starting = datetime(2011, int(mo), int(da), int(starth))
        ending = datetime(2011, int(mo), int(da), int(endh))
        servings = reduce(lambda ss, d: ss + maybe([], cls._scrape_servings, d, starting, ending),
                          spliz(r"<p.*?>", menu),
                          [])
        return servings

    @classmethod
    def _scrape_servings(cls, menu, starting, ending):
        name, eur, cnt = match(r"(.*?) (\d+),(\d+) *<br", menu).groups()
        servings = [Serving(name=name, price=[int(eur) * 100 + int(cnt)], start=starting, end=ending)]
        return servings
