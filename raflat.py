# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import htmlentitydefs
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
    for enc in ('utf-8', 'iso-8859-15', 'iso-8859-1', 'utf-16'):
        if re.search("text/html; charset=%s" % enc, content, re.I):
            return content.decode(enc)
    try:
        return content.decode('utf-8')
    except UnicodeDecodeError:
        # just wrap
        return unicode(content)

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

def searchx(pattern, string):
    return re.search(pattern, string, re.I | re.U | re.S | re.X)

def strptime(datestr, *patterns):
    for p in patterns:
        try:
            return datetime.strptime('%d-%s' % (datetime.now().year, datestr), '%Y-' + p)
        except ValueError, err:
            pass
    raise err

def dec_ents(string):
    while True:
        m= re.search('&(\w{4});', string)
        if not m:
            break
        string = string[:m.start()] \
                 + unichr(htmlentitydefs.name2codepoint[m.group(1)]) \
                 + string[m.end():]
    return string


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
            price = u'%.2f€-%.2f€' % (self.price[0] / 100., self.price[-1] / 100.)
        elif self.price[0:]:
            price = u'%.2f€' % (self.price[0] / 100.)
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
            search(ur"Lounaslista.*?klo (\d+).(\d+).+?(\d+).(\d+)(.*)<strong>TERVETULOA!", decode_content(rs)).groups()
        start = timedelta(hours=int(starth), minutes=int(startm))
        end = timedelta(hours=int(endh), minutes=int(endm))
        servings = reduce(lambda ss, daymenu:
                              ss + maybe([], cls._scrape_servings, daymenu, start, end),
                          spliz(r"<strong>\w+ (?=\d+\.\d+)", menu),
                          [])
        return servings

    @classmethod
    def _scrape_servings(cls, menu, start, end):
        damo, basic, dessert, value = \
            match(ur"(\d+\.\d+).+?<p>(.+)Jälkiruoka(.*)Grillistä(.+)", menu).groups()
        start = strptime(damo, '%d.%m') + start
        end = strptime(damo, '%d.%m') + end
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
        starth, endh, damo, menu = \
            search(ur"arkisin klo (\d+)-(\d+).*?LOUNAS .*? (\d+\.\d+)(.*)Albertinkatu", decode_content(rs)).groups()
        start = strptime(damo, '%d.%m') + timedelta(hours=int(starth))
        end = strptime(damo, '%d.%m') + timedelta(hours=int(endh))
        servings = reduce(lambda ss, daymenu:
                              ss + maybe([], cls._scrape_servings, daymenu, start, end),
                          spliz(r"<p.*?>", menu),
                          [])
        return servings

    @classmethod
    def _scrape_servings(cls, menu, start, end):
        name, eur, cnt = match(r"(.*?) (\d+),(\d+) *<br", menu).groups()
        servings = [Serving(name=name, price=[int(eur) * 100 + int(cnt)], start=start, end=end)]
        return servings


class KonstanMolja(BaseRafla):
    @classmethod
    def scrape_menu(cls):
        rs = urlfetch.fetch("http://www.kolumbus.fi/konstanmolja/lounas_fi.html")
        assert rs.status_code == 200
        start, end, eur, cnt, week, menu = \
            search(ur"Ti-.*? (\d+.\d+)-(\d+.\d+).*?(\d+),(\d+).*?vko (\d+)(.*)", decode_content(rs)).groups()
        # calculating from monday to avoid complications with partial weeks
        basedates = [strptime('%s-0 %s' % (week, start), '%U-%w %H.%M'),
                     strptime('%s-0 %s' % (week, end), '%U-%w %H.%M')]
        dates = lambda i: [d + timedelta(days=1 + i) for d in basedates]
        price = int(eur) * 100 + int(cnt)
        # consuming one i here for the foobar fragment before Tuesday's menu
        servings = reduce(lambda ss, (i, daymenu):
                              ss + maybe([],
                                         cls._scrape_servings,
                                         daymenu,
                                         price,
                                         *dates(i)),
                          enumerate(spliz(r'<div align="center">', menu)),
                          [])
        return servings

    @classmethod
    def _scrape_servings(cls, menu, price, start, end):
        servings = [Serving(name=dec_ents(name), price=[price], start=start, end=end)
                    for name in spliz(r"<.+>", menu)]
        if servings[1:]:
            servings[-1].food_type = ['dessert']
        return servings


class RavintolaVPK(BaseRafla):
    @classmethod
    def scrape_menu(cls):
        rs = urlfetch.fetch("http://www.restaurantwalhalla.com/vpk/lounas.php")
        assert rs.status_code == 200
        startd, mo, startt, endt, eur, cnt, menu, special = \
            searchx(ur"""
                viikko.*?(\d+)-\d+.(\d+) +([\d\.]+).+?([\d\.]+).*
                kotiruoka.(\d+),(\d+) # price
                (.*) # homefood menu
                Keittiömestarin.suositus:
                (.*) # "special" menu
                Lounas.sisältää
                """, decode_content(rs)).groups()
        basedates = [strptime('%s-%s %s' % (mo, startd, t), '%m-%d %H.%M', '%m-%d %H')
                     for t in [startt, endt]]
        dates = lambda i: [d + timedelta(days=1 + i) for d in basedates]
        price = int(eur) * 100 + int(cnt)
        # first parse the basic foods
        servings = [(i, maybe([], cls._scrape_basic, daymenu, price, *dates(i)))
                    for i, daymenu in enumerate(spliz(r'<br>\w{2} <b>', menu))]
        # then decorate every successful parse with specials
        servings = reduce(lambda ss, (i, m):
                              ss + m + (maybe([], cls._scrape_special, special, *dates(i)) if m else []),
                          servings,
                          [])
        return servings

    @classmethod
    def _scrape_basic(cls, menu, price, start, end):
        return [Serving(name=dec_ents(name), price=[price], start=start, end=end)
                for name in spliz(r"<.+>", menu)]

    @classmethod
    def _scrape_special(cls, menu, start, end):
        return [Serving(name=dec_ents(name), price=[int(eur) * 100 + int(cnt)], start=start, end=end)
                for name, eur, cnt
                in [search(" *(.*) +(\d+),(\d+)", m).groups() for m in spliz(r"<.+?>", menu)]]
