# coding=utf-8

# python 2.7/3.5 compatible
from queue import Queue
from builtins import chr
from builtins import str as text
from builtins import str

from io import StringIO
from past.builtins import xrange

from html.entities import name2codepoint
from future.moves.itertools import zip_longest

try:
    import itertools.izip as zip
except ImportError:
    pass

import argparse
import bz2
import codecs
import io
import logging
import multiprocessing
import os.path
import os.path
import re  # TODO use regex when it will be standard
import sys
import threading
import time
import urllib
from bz2 import BZ2File

from lxml import etree

import wiki_infobox

# from es_text_analytics.data.dataset import Dataset

"""
Dataset extracting article content and some metadata from Wikipedia dumps.

https://dumps.wikimedia.org/backup-index.html
"""


# XSLT stylesheet that removes namespaces.
# simplifies information extraction from the XML dump format since we don't need to
# match namespaces when searching for elements.
remove_ns_xslt = '''
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
    <xsl:output method="xml" indent="no"/>

    <xsl:template match="/|comment()|processing-instruction()">
        <xsl:copy>
          <xsl:apply-templates/>
        </xsl:copy>
    </xsl:template>

    <xsl:template match="*">
        <xsl:element name="{local-name()}">
          <xsl:apply-templates select="@*|node()"/>
        </xsl:element>
    </xsl:template>

    <xsl:template match="@*">
        <xsl:attribute name="{local-name()}">
          <xsl:value-of select="."/>
        </xsl:attribute>
    </xsl:template>
</xsl:stylesheet>
'''

remove_ns_transform = etree.XSLT(etree.parse(io.BytesIO(remove_ns_xslt.encode())))


def remove_ns(element):
    """
    Removes namespaces from etree XML document elements.

    :param element: An Etree XML node element.
    :type element: etree.Element
    :rtype : etree.Element
    :return: XML document node with namespaces removed.
    """
    return remove_ns_transform(element).getroot()


class StringWrapper(object):
    """
    Simple wrapper class redirecting WikiExtractor output to a string.

    Accepts and returns unicode strings.
    """

    def __init__(self):
        super(StringWrapper, self).__init__()

        self.inner = u''

    def open(self, fn):
        pass

    def reserve(self, size):
        pass

    def close(self):
        pass

    def write(self, data):
        self.inner += data.decode('utf-8')

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)


def extract_metadata(element, tags=None):
    """
    Extracts (meta)data embedded in the XML dump structure.

    Includes the article content from the revision node.

    Recursively traverses the XML structure and collects all tag name/text pairs.

    :param element: XML node as Etree element.
    :type element: etree.Element
    :param tags: Element tags under the passed node. Will be prefixed to metadata identifier.
    :rtype : list[tuple[unicode|str, unicode|str]]
    :return: A list of identifier/value tuples.
    """
    if not tags:
        tags = []

    metadata = []

    for child in element.getchildren():
        elt_tag = tags + [child.tag]
        text = child.text

        if text:
            text = text.strip()
        else:
            text = ''

        metadata.append(('.'.join(elt_tag), text))

        metadata += extract_metadata(child, elt_tag)

    return metadata


def extract_page(element):
    """
    Extracts page metadata and text content.

    :param element: XML page element from dump.
    :type element: etree.Element
    :rtype : dict
    :return: A dictionary with data/metadata identifier/value pairs.
    """
    # get metadata/data
    metadata = dict(extract_metadata(element))

    infometa = None
    if 'revision.text' in metadata:
        infometa = wiki_infobox.scrape_infobox(metadata['revision.text'])

    if infometa:
        metadata['infoboks'] = infometa

    # extract text using WikiExtractor
    e = Extractor(int(metadata['id']), metadata['title'], metadata['revision.text'])
    Extractor.toHTML = False
    out = StringIO()
    e.extract(out=out)
    metadata['article.text'] = out.getvalue()

    # parse some of the metadata
    metadata['id'] = int(metadata['id']) if metadata.get('id', '') != '' else -1
    metadata['revision.id'] = int(metadata['revision.id']) if metadata.get('revision.id', '') != '' else -1
    metadata['revision.parentid'] = int(metadata['revision.parentid']) if metadata.get('revision.parentid',
                                                                                       '') != '' else -1
    metadata['revision.contributor.id'] = int(metadata['revision.contributor.id']) if metadata.get(
        'revision.contributor.id', '') != '' else -1

    return metadata


def _extract_page_pickle_friendly(e):
    page = extract_page(etree.fromstring(e))

    return page


def article_gen(dump_fn, num_articles=None, parse=True, n_procs=1):
    """
    Yields the page content and metadata as dicts.

    :param num_articles: how many articles. 0 means all
    :param dump_fn: BZip2 copressed Wikipedia XML dump.
    :type dump_fn: unicode|str
    :rtype : generator
    """
    if parse:
        pool = multiprocessing.Pool(processes=n_procs)

        for data in pool.map(_extract_page_pickle_friendly, _article_gen_inner(dump_fn, num_articles=num_articles)):
            if 'revision.text' in data:
                if data['revision.text'][0:9] == '#REDIRECT':
                    continue

            # filter out empty crap
            if len(data['article.text']) < 30:
                continue

            if data['title'].startswith('Wikipedia:'):
                continue

            yield data
    else:
        for data in _article_gen_inner(dump_fn, num_articles=num_articles):
            yield data


def _article_gen_inner(dump_fn, num_articles=None):
    counter = 0

    if os.path.splitext(dump_fn)[1] == '.bz2':
        f = BZ2File(dump_fn)
    else:
        f = open(dump_fn)

    for _, element in etree.iterparse(f): #, tag='{http://www.mediawiki.org/xml/export-0.8/}page'):
        try:
            no_ns_elt = remove_ns(element)

            if no_ns_elt.tag == 'page':
                yield etree.tostring(no_ns_elt)

                no_ns_elt.clear()
                element.clear()

                counter += 1

                # Also eliminate now-empty references from the root node to elem
                # for ancestor in element.xpath('ancestor-or-self::*'):
                while element.getprevious() is not None:
                    del element.getparent()[0]

                while no_ns_elt.getprevious() is not None:
                    del no_ns_elt.getparent()[0]

                if num_articles and num_articles <= counter:
                    return
            elif no_ns_elt.tag == 'logitem' or no_ns_elt.tag == 'siteinfo':
                no_ns_elt.clear()
                element.clear()

                while element.getprevious() is not None:
                    del element.getparent()[0]

                while no_ns_elt.getprevious() is not None:
                    del no_ns_elt.getparent()[0]
        except Exception as e:
            logging.error("Element parse failed with exception %s, message %s" % (type(e), e.message))
            continue

    f.close()


# From WikiExtractor.py
# The following code is adapted from http://medialab.di.unipi.it/wiki/Wikipedia_Extractor

# !/usr/bin/python
# -*- coding: utf-8 -*-
#
# =============================================================================
#  Version: 2.32 (Apr 26, 2015)
#  Author: Giuseppe Attardi (attardi@di.unipi.it), University of Pisa
#
#  Contributors:
#  Antonio Fuschetto (fuschett@aol.com)
#  Leonardo Souza (lsouza@amtera.com.br)
#  Juan Manuel Caicedo (juan@cavorite.com)
#  Humberto Pereira (begini@gmail.com)
#  Siegfried-A. Gevatter (siegfried@gevatter.com)
#  Pedro Assis (pedroh2306@gmail.com)
#  Wim Muskee (wimmuskee@gmail.com)
#  Radics Geza (radicsge@gmail.com)
#
# =============================================================================
#  Copyright (c) 2009-2015. Giuseppe Attardi (attardi@di.unipi.it).
# =============================================================================
#  This file is part of Tanl.
#
#  Tanl is free software; you can redistribute it and/or modify it
#  under the terms of the GNU General Public License, version 3,
#  as published by the Free Software Foundation.
#
#  Tanl is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
# =============================================================================

"""Wikipedia Extractor:
Extracts and cleans text from a Wikipedia database dump and stores output in a
number of files of similar size in a given directory.
Each file will contain several documents in the format:

<doc id="" url="" title="">
  ...
</doc>

This version performs template expansion by preprocesssng the whole dump and
collecting template definitions.
"""

# ===========================================================================

# Program version
version = '2.32'

# PARAMS

##
# Defined in <siteinfo>
# We include as default Template, when loading external template file.
knownNamespaces = {'Template'}

##
# The namespace used for template definitions
templateNamespace = 'Template'

##
# Recognize only these namespaces
# w: Internal links to the Wikipedia
# wiktionary: Wiki dictionary
# wikt: shortcut for Wiktionary
#
acceptedNamespaces = ['w', 'wiktionary', 'wikt']

##
# Drop these elements from article text
#
discardElements = [
    'gallery', 'timeline', 'noinclude', 'pre',
    'table', 'tr', 'td', 'th', 'caption', 'div',
    'form', 'input', 'select', 'option', 'textarea',
    'ul', 'li', 'ol', 'dl', 'dt', 'dd', 'menu', 'dir',
    'ref', 'references', 'img', 'imagemap', 'source', 'small'
]

# This is obtained from <siteinfo>
urlbase = None


def get_url(page_id):
    global urlbase
    return "%s?curid=%s" % (urlbase, page_id)


# =========================================================================
#
# MediaWiki Markup Grammar
# https://www.mediawiki.org/wiki/Preprocessor_ABNF

# xml-char = %x9 / %xA / %xD / %x20-D7FF / %xE000-FFFD / %x10000-10FFFF
# sptab = SP / HTAB

# ; everything except ">" (%x3E)
# attr-char = %x9 / %xA / %xD / %x20-3D / %x3F-D7FF / %xE000-FFFD / %x10000-10FFFF

# literal         = *xml-char
# title           = wikitext-L3
# part-name       = wikitext-L3
# part-value      = wikitext-L3
# part            = ( part-name "=" part-value ) / ( part-value )
# parts           = [ title *( "|" part ) ]
# tplarg          = "{{{" parts "}}}"
# template        = "{{" parts "}}"
# link            = "[[" wikitext-L3 "]]"

# comment         = "<!--" literal "-->"
# unclosed-comment = "<!--" literal END
# ; the + in the line-eating-comment rule was absent between MW 1.12 and MW 1.22
# line-eating-comment = LF LINE-START *SP +( comment *SP ) LINE-END

# attr            = *attr-char
# nowiki-element  = "<nowiki" attr ( "/>" / ( ">" literal ( "</nowiki>" / END ) ) )

# wikitext-L2     = heading / wikitext-L3 / *wikitext-L2
# wikitext-L3     = literal / template / tplarg / link / comment /
#                   line-eating-comment / unclosed-comment / xmlish-element /
#                   *wikitext-L3

# ------------------------------------------------------------------------------

selfClosingTags = ['br', 'hr', 'nobr', 'ref', 'references', 'nowiki']

# These tags are dropped, keeping their content.
# handle 'a' separately, depending on keepLinks
ignoredTags = [
    'abbr', 'b', 'big', 'blockquote', 'center', 'cite', 'div', 'em',
    'font', 'h1', 'h2', 'h3', 'h4', 'hiero', 'i', 'kbd', 'nowiki',
    'p', 'plaintext', 's', 'span', 'strike', 'strong',
    'sub', 'sup', 'tt', 'u', 'var'
]

placeholder_tags = {'math': 'formula', 'code': 'codice'}

re_title_sub = re.compile(r'[\s_]+')
re_title_match = re.compile(r'([^:]*):(\s*)(\S(?:.*))')

def normalize_title(title):
    """Normalize title"""
    # remove leading/trailing whitespace and underscores
    title = title.strip(' _')
    # replace sequences of whitespace and underscore chars with a single space
    title = re_title_sub.sub(' ', title)

    m = re_title_match.match(title)

    if m:
        prefix = m.group(1)
        if m.group(2):
            optional_whitespace = ' '
        else:
            optional_whitespace = ''
        rest = m.group(3)

        ns = normalize_namespace(prefix)
        if ns in knownNamespaces:
            # If the prefix designates a known namespace, then it might be
            # followed by optional whitespace that should be removed to get
            # the canonical page name
            # (e.g., "Category:  Births" should become "Category:Births").
            title = ns + ":" + ucfirst(rest)
        else:
            # No namespace, just capitalize first letter.
            # If the part before the colon is not a known namespace, then we
            # must not remove the space after the colon (if any), e.g.,
            # "3001: The_Final_Odyssey" != "3001:The_Final_Odyssey".
            # However, to get the canonical page name we must contract multiple
            # spaces into one, because
            # "3001:   The_Final_Odyssey" != "3001: The_Final_Odyssey".
            title = ucfirst(prefix) + ":" + optional_whitespace + ucfirst(rest)
    else:
        # no namespace, just capitalize first letter
        title = ucfirst(title)
    return title


##
# Removes HTML or XML character references and entities from a text string.
#
# @param text The HTML (or XML) source text.
# @return The plain text, as a Unicode string, if necessary.

re_unescape_fixup = re.compile("&#?(\w+);")

def unescape(text):
    def fixup(m):
        inner_text = m.group(0)
        code = m.group(1)
        # noinspection PyBroadException
        try:
            if inner_text[1] == "#":  # character reference
                if inner_text[2] == "x":
                    return chr(int(code[1:], 16))
                else:
                    return chr(int(code))
            else:  # named entity
                return chr(name2codepoint[code])
        except:
            return inner_text  # leave as is

    return re_unescape_fixup.sub(fixup, text)


# Match HTML comments
# The buggy template {{Template:T}} has a comment terminating with just "->"
comment = re.compile(r'<!--.*?-->', re.DOTALL)

# Match ignored tags
ignored_tag_patterns = []


def ignore_tag(elt_tag):
    left = re.compile(r'<%s\b[^>/]*>' % elt_tag, re.IGNORECASE)  # both <ref> and <reference>
    right = re.compile(r'</\s*%s>' % elt_tag, re.IGNORECASE)
    ignored_tag_patterns.append((left, right))


for tag in ignoredTags:
    ignore_tag(tag)

# Match selfClosing HTML tags
selfClosing_tag_patterns = \
    [re.compile(r'<\s*%s\b[^>]*/\s*>' % tag, re.DOTALL | re.IGNORECASE) for tag in selfClosingTags]

# Match HTML placeholder tags
placeholder_tag_patterns = \
    [(re.compile(r'<\s*%s(\s*| [^>]+?)>.*?<\s*/\s*%s\s*>' % (tag, tag), re.DOTALL | re.IGNORECASE), repl)
     for tag, repl in placeholder_tags.items()]

# Match preformatted lines
preformatted = re.compile(r'^ .*?$')

# Match external links (space separates second optional parameter)
externalLink = re.compile(r'\[\w+[^ ]*? (.*?)]')
externalLinkNoAnchor = re.compile(r'\[\w+[&\]]*\]')

# Matches bold/italic
bold_italic = re.compile(r"'''''(.*?)'''''")
bold = re.compile(r"'''(.*?)'''")
italic_quote = re.compile(r"''\"([^\"]*?)\"''")
italic = re.compile(r"''(.*?)''")
quote_quote = re.compile(r'""([^"]*?)""')

# Matches space
spaces = re.compile(r' {2,}')

# Matches dots
dots = re.compile(r'\.{4,}')


# ======================================================================

class Template(list):
    """
    A Template is a list of TemplateText or TemplateArgs
    """

    @classmethod
    def parse(cls, body):
        tpl = Template()
        # we must handle nesting, s.a.
        # {{{1|{{PAGENAME}}}
        # {{{italics|{{{italic|}}}
        # {{#if:{{{{{#if:{{{nominee|}}}|nominee|candidate}}|}}}|
        #
        start = 0
        for s, e in find_matching_braces(body, 3):
            tpl.append(TemplateText(body[start:s]))
            tpl.append(TemplateArg(body[s + 3:e - 3]))
            start = e
        tpl.append(TemplateText(body[start:]))  # leftover
        return tpl

    def subst(self, params, extractor, depth=0):
        # We perform parameter substitutions recursively.
        # We also limit the maximum number of iterations to avoid too long or
        # even endless loops (in case of malformed input).

        # :see: http://meta.wikimedia.org/wiki/Help:Expansion#Distinction_between_variables.2C_parser_functions.2C_and_templates
        #
        # Parameter values are assigned to parameters in two (?) passes.
        # Therefore a parameter name in a template can depend on the value of
        # another parameter of the same template, regardless of the order in
        # which they are specified in the template call, for example, using
        # Template:ppp containing "{{{{{{p}}}}}}", {{ppp|p=q|q=r}} and even
        # {{ppp|q=r|p=q}} gives r, but using Template:tvvv containing
        # "{{{{{{{{{p}}}}}}}}}", {{tvvv|p=q|q=r|r=s}} gives s.

        logging.debug('subst tpl (%d, %d) %s', len(extractor.frame), depth, self)

        if depth > extractor.maxParameterRecursionLevels:
            logging.warn('Reachead maximum parameter recursions: %d',
                         extractor.maxParameterRecursionLevels)
            return ''

        return ''.join([tpl.subst(params, extractor, depth) for tpl in self])

    def __str__(self):
        return ''.join([text(x) for x in self])


class TemplateText(text):
    """Fixed text of template"""

    # noinspection PyUnusedLocal
    def subst(self, params, extractor, depth):
        return self


class TemplateArg(object):
    """
    parameter to a template.
    Has a name and a default value, both of which are Templates.
    """

    def __init__(self, parameter):
        """
        :param parameter: the parts of a tplarg.
        """
        # the parameter name itself might contain templates, e.g.:
        #   appointe{{#if:{{{appointer14|}}}|r|d}}14|
        #   4|{{{{{subst|}}}CURRENTYEAR}}

        # any parts in a tplarg after the first (the parameter default) are
        # ignored, and an equals sign in the first part is treated as plain text.
        # logging.debug('TemplateArg %s', parameter)

        parts = split_parts(parameter)
        self.name = Template.parse(parts[0])
        if len(parts) > 1:
            # This parameter has a default value
            self.default = Template.parse(parts[1])
        else:
            self.default = None

    def __str__(self):
        if self.default:
            return '{{{%s|%s}}}' % (self.name, self.default)
        else:
            return '{{{%s}}}' % self.name

    def subst(self, params, extractor, depth):
        """
        Substitute value for this argument from dict :param params:
        Use :param extractor: to evaluate expressions for name and default.
        Limit substitution to the maximun :param depth:.
        """
        # the parameter name itself might contain templates, e.g.:
        # appointe{{#if:{{{appointer14|}}}|r|d}}14|
        param_name = self.name.subst(params, extractor, depth + 1)
        param_name = extractor.expand_templates(param_name)
        res = ''
        if param_name in params:
            res = params[param_name]  # use parameter value specified in template invocation
        elif self.default:  # use the default value
            default_value = self.default.subst(params, extractor, depth + 1)
            res = extractor.expand_templates(default_value)
        logging.debug('subst arg %d %s -> %s' % (depth, param_name, res))
        return res


# ======================================================================

substWords = 'subst:|safesubst:'
re_subst_words = re.compile(substWords, re.IGNORECASE)

RE_PARAM = re.compile(' *([^= ]*?) *=(.*)', re.DOTALL)

class Extractor(object):
    """
    An extraction task on a article.
    """
    ##
    # Whether to preserve links in output
    keepLinks = False

    ##
    # Whether to transform sections into HTML
    keepSections = False

    ##
    # Whether to output HTML instead of text
    toHTML = False

    def __init__(self, page_id, title, page):
        """
        :param page: a list of lines.
        """
        self.id = page_id
        self.title = title
        self.page = page
        self.magicWords = MagicWords()
        self.frame = []

    def extract(self, out=sys.stdout):
        logging.debug("%s\t%s", self.id, self.title)
        text = ''.join(self.page)
        url = get_url(self.id)
     #   header = '<doc id="%s" url="%s" title="%s">\n' % (self.id, url, self.title)

        # Separate header from text with a newline.
        #header += self.title + '\n\n'
        #header = header.encode('utf-8')
        self.magicWords['pagename'] = self.title
        self.magicWords['fullpagename'] = self.title
        self.magicWords['currentyear'] = time.strftime('%Y')
        self.magicWords['currentmonth'] = time.strftime('%m')
        self.magicWords['currentday'] = time.strftime('%d')
        self.magicWords['currenthour'] = time.strftime('%H')
        self.magicWords['currenttime'] = time.strftime('%H:%M:%S')
        text = clean(self, text)
        #footer = "\n</doc>\n"
        if out != sys.stdout and not isinstance(out, StringIO):
         #   out.reserve(len(header) + len(text) + len(footer))
          out.reserve(len(text))
        #out.write(header)
        for line in compact(text):
            out.write(line)
            out.write(u'\n')
    #    out.write(footer)

    # ----------------------------------------------------------------------
    # Expand templates

    maxTemplateRecursionLevels = 30
    maxParameterRecursionLevels = 10

    # check for template beginning
    reOpen = re.compile('(?<!{){{(?!{)', re.DOTALL)

    def expand_templates(self, wikitext):
        """
        :param wikitext: the text to be expanded.

        Templates are frequently nested. Occasionally, parsing mistakes may
        cause template insertion to enter an infinite loop, for instance when
        trying to instantiate Template:Country

        {{country_{{{1}}}|{{{2}}}|{{{2}}}|size={{{size|}}}|name={{{name|}}}}}

        which is repeatedly trying to insert template 'country_', which is
        again resolved to Template:Country. The straightforward solution of
        keeping track of templates that were already inserted for the current
        article would not work, because the same template may legally be used
        more than once, with different parameters in different parts of the
        article.  Therefore, we limit the number of iterations of nested
        template inclusion.

        """
        # Test template expansion at:
        # https://en.wikipedia.org/wiki/Special:ExpandTemplates

        res = ''
        if len(self.frame) >= self.maxTemplateRecursionLevels:
            logging.warn('Max template recursion exceeded!')
            return res

        # logging.debug('<expandTemplates ' + str(len(self.frame)))

        cur = 0
        # look for matching {{...}}
        for s, e in find_matching_braces(wikitext, 2):
            res += wikitext[cur:s] + self.expand_template(wikitext[s + 2:e - 2])
            cur = e
        # leftover
        res += wikitext[cur:]
        if cur:
            logging.debug('   expandTemplates> %d %s', len(self.frame), res)
        return res

    # noinspection PyMethodMayBeStatic
    def template_params(self, parameters):
        """
        Build a dictionary with positional or name key to expanded parameters.
        :param parameters: the parts[1:] of a template, i.e. all except the title.
        """
        template_params = {}

        if not parameters:
            return template_params
        logging.debug('<template_params: %s', '|'.join(parameters))

        # Parameters can be either named or unnamed. In the latter case, their
        # name is defined by their ordinal position (1, 2, 3, ...).

        unnamed_parameter_counter = 0

        # It's legal for unnamed parameters to be skipped, in which case they
        # will get default values (if available) during actual instantiation.
        # That is {{template_name|a||c}} means parameter 1 gets
        # the value 'a', parameter 2 value is not defined, and parameter 3 gets
        # the value 'c'.  This case is correctly handled by function 'split',
        # and does not require any special handling.
        for param in parameters:
            # Spaces before or after a parameter value are normally ignored,
            # UNLESS the parameter contains a link (to prevent possible gluing
            # the link to the following text after template substitution)

            # Parameter values may contain "=" symbols, hence the parameter
            # name extends up to the first such symbol.

            # It is legal for a parameter to be specified several times, in
            # which case the last assignment takes precedence. Example:
            # "{{t|a|b|c|2=B}}" is equivalent to "{{t|a|B|c}}".
            # Therefore, we don't check if the parameter has been assigned a
            # value before, because anyway the last assignment should override
            # any previous ones.
            # FIXME: Don't use DOTALL here since parameters may be tags with
            # attributes, e.g. <div class="templatequotecite">
            # Parameters may span several lines, like:
            # {{Reflist|colwidth=30em|refs=
            # &lt;ref name=&quot;Goode&quot;&gt;Title&lt;/ref&gt;

            # The '=' might occurr within an HTML attribute:
            #   "&lt;ref name=value"
            # but we stop at first.
            m = RE_PARAM.match(param)

            if m:
                # This is a named parameter.  This case also handles parameter
                # assignments like "2=xxx", where the number of an unnamed
                # parameter ("2") is specified explicitly - this is handled
                # transparently.

                parameter_name = m.group(1).strip()
                parameter_value = m.group(2)

                if ']]' not in parameter_value:  # if the value does not contain a link, trim whitespace
                    parameter_value = parameter_value.strip()
                template_params[parameter_name] = parameter_value
            else:
                # this is an unnamed parameter
                unnamed_parameter_counter += 1

                if ']]' not in param:  # if the value does not contain a link, trim whitespace
                    param = param.strip()
                template_params[str(unnamed_parameter_counter)] = param
        logging.debug('   template_params> %s', '|'.join(template_params.values()))
        return template_params

    def expand_template(self, body):
        """Expands template invocation.
        :param body: the parts of a template.

        :see http://meta.wikimedia.org/wiki/Help:Expansion for an explanation
        of the process.

        See in particular: Expansion of names and values
        http://meta.wikimedia.org/wiki/Help:Expansion#Expansion_of_names_and_values

        For most parser functions all names and values are expanded,
        regardless of what is relevant for the result. The branching functions
        (#if, #ifeq, #iferror, #ifexist, #ifexpr, #switch) are exceptions.

        All names in a template call are expanded, and the titles of the
        tplargs in the template body, after which it is determined which
        values must be expanded, and for which tplargs in the template body
        the first part (default).

        In the case of a tplarg, any parts beyond the first are never
        expanded.  The possible name and the value of the first part is
        expanded if the title does not match a name in the template call.

        :see code for braceSubstitution at
        https://doc.wikimedia.org/mediawiki-core/master/php/html/Parser_8php_source.html#3397:

        """

        # template        = "{{" parts "}}"

        # Templates and tplargs are decomposed in the same way, with pipes as
        # separator, even though eventually any parts in a tplarg after the first
        # (the parameter default) are ignored, and an equals sign in the first
        # part is treated as plain text.
        # Pipes inside inner templates and tplargs, or inside double rectangular
        # brackets within the template or tplargs are not taken into account in
        # this decomposition.
        # The first part is called title, the other parts are simply called parts.

        # If a part has one or more equals signs in it, the first equals sign
        # determines the division into name = value. Equals signs inside inner
        # templates and tplargs, or inside double rectangular brackets within the
        # part are not taken into account in this decomposition. Parts without
        # equals sign are indexed 1, 2, .., given as attribute in the <name> tag.

        if len(self.frame) >= self.maxTemplateRecursionLevels:
            logging.warn('Reached max template recursion: %d',
                         self.maxTemplateRecursionLevels)
            logging.debug('   INVOCATION> %d %s', len(self.frame), body)
            return ''

        logging.debug('INVOCATION %d %s', len(self.frame), body)

        parts = split_parts(body)
        # title is the portion before the first |
        logging.debug('TITLE %s', parts[0].strip())
        title = self.expand_templates(parts[0].strip())

        # SUBST
        # Apply the template tag to parameters without
        # substituting into them, e.g.
        # {{subst:t|a{{{p|q}}}b}} gives the wikitext start-a{{{p|q}}}b-end
        # @see https://www.mediawiki.org/wiki/Manual:Substitution#Partial_substitution
        subst = False

        if re_subst_words.match(title):
            # title = re.sub(substWords, '', title, 1, re.IGNORECASE)
            title = re_subst_words.sub('', title, 1)
            subst = True

        if title.lower() in self.magicWords.values:
            return self.magicWords[title.lower()]

        # Parser functions
        # The first argument is everything after the first colon.
        # It has been evaluated above.
        colon = title.find(':')
        if colon > 1:
            funct = title[:colon]
            parts[0] = title[colon + 1:].strip()  # side-effect (parts[0] not used later)
            # arguments after first are not evaluated
            ret = call_parser_function(funct, parts, self.frame)
            return self.expand_templates(ret)

        title = fully_qualified_template_title(title)

        redirected = redirects.get(title)
        if redirected:
            title = redirected

        # get the template
        if title in templateCache:
            template = templateCache[title]
        elif title in templates:
            template = Template.parse(templates[title])
            # add it to cache
            templateCache[title] = template
            del templates[title]
        else:
            # The page being included could not be identified
            return ''

        logging.debug('TEMPLATE %s: %s', title, template)

        # tplarg          = "{{{" parts "}}}"
        # parts           = [ title *( "|" part ) ]
        # part            = ( part-name "=" part-value ) / ( part-value )
        # part-name       = wikitext-L3
        # part-value      = wikitext-L3
        # wikitext-L3     = literal / template / tplarg / link / comment /
        #                   line-eating-comment / unclosed-comment /
        # xmlish-element / *wikitext-L3

        # A tplarg may contain other parameters as well as templates, e.g.:
        #   {{{text|{{{quote|{{{1|{{error|Error: No text given}}}}}}}}}}}
        # hence no simple RE like this would work:
        #   '{{{((?:(?!{{{).)*?)}}}'
        # We must use full CF parsing.

        # the parameter name itself might be computed, e.g.:
        #   {{{appointe{{#if:{{{appointer14|}}}|r|d}}14|}}}

        # Because of the multiple uses of double-brace and triple-brace
        # syntax, expressions can sometimes be ambiguous.
        # Precedence rules specifed here:
        # http://www.mediawiki.org/wiki/Preprocessor_ABNF#Ideal_precedence
        # resolve ambiguities like this:
        #   {{{{ }}}} -> { {{{ }}} }
        #   {{{{{ }}}}} -> {{ {{{ }}} }}
        #
        # :see: https://en.wikipedia.org/wiki/Help:Template#Handling_parameters

        params = parts[1:]

        if not subst:
            # Evaluate parameters, since they may contain templates, including
            # the symbol "=".
            # {{#ifexpr: {{{1}}} = 1 }}
            params = [self.expand_templates(p) for p in params]

        # build a dict of name-values for the parameter values
        params = self.template_params(params)

        # Perform parameter substitution
        instantiated = template.subst(params, self)
        logging.debug('instantiated %d %s', len(self.frame), instantiated)
        self.frame.append((title, params))
        value = self.expand_templates(instantiated)
        self.frame.pop()
        logging.debug('   INVOCATION> %s %d %s', title, len(self.frame), value)
        return value


# ----------------------------------------------------------------------
# parameter handling

def split_parts(params_list):
    """
    :param params_list: the parts of a template or tplarg.

    Split template parameters at the separator "|".
    separator "=".

    Template parameters often contain URLs, internal links, text or even
    template expressions, since we evaluate templates outside in.
    This is required for cases like:
      {{#if: {{{1}}} | {{lc:{{{1}}} | "parameter missing"}}
    Parameters are separated by "|" symbols. However, we
    cannot simply split the string on "|" symbols, since these
    also appear inside templates and internal links, e.g.

     {{if:|
      |{{#if:the president|
           |{{#if:|
               [[Category:Hatnote templates|A{{PAGENAME}}]]
            }}
       }}
     }}

    We split parts at the "|" symbols that are not inside any pair
    {{{...}}}, {{...}}, [[...]], {|...|}.
    """

    # Must consider '[' as normal in expansion of Template:EMedicine2:
    # #ifeq: ped|article|[http://emedicine.medscape.com/article/180-overview|[http://www.emedicine.com/ped/topic180.htm#{{#if: |section~}}
    # as part of:
    # {{#ifeq: ped|article|[http://emedicine.medscape.com/article/180-overview|[http://www.emedicine.com/ped/topic180.htm#{{#if: |section~}}}} ped/180{{#if: |~}}]

    # should handle both tpl arg like:
    #    4|{{{{{subst|}}}CURRENTYEAR}}
    # and tpl parameters like:
    #    ||[[Category:People|{{#if:A|A|{{PAGENAME}}}}]]

    sep = '|'
    parameters = []
    cur = 0
    for s, e in find_matching_braces(params_list):
        par = params_list[cur:s].split(sep)
        if par:
            if parameters:
                # portion before | belongs to previous parameter
                parameters[-1] += par[0]
                if len(par) > 1:
                    # rest are new parameters
                    parameters.extend(par[1:])
            else:
                parameters = par
        elif not parameters:
            parameters = ['']  # create first param
        # add span to last previous parameter
        parameters[-1] += params_list[s:e]
        cur = e
    # leftover
    par = params_list[cur:].split(sep)
    if par:
        if parameters:
            # portion before | belongs to previous parameter
            parameters[-1] += par[0]
            if len(par) > 1:
                # rest are new parameters
                parameters.extend(par[1:])
        else:
            parameters = par

    # logging.debug('splitParts %s %s\nparams: %s', sep, params_list, str(parameters))
    return parameters


def find_matching_braces(text, ldelim=0):
    """
    :param ldelim: number of braces to match. 0 means match [[]], {{}} and {{{}}}.
    """
    # Parsing is done with respect to pairs of double braces {{..}} delimiting
    # a template, and pairs of triple braces {{{..}}} delimiting a tplarg.
    # If double opening braces are followed by triple closing braces or
    # conversely, this is taken as delimiting a template, with one left-over
    # brace outside it, taken as plain text. For any pattern of braces this
    # defines a set of templates and tplargs such that any two are either
    # separate or nested (not overlapping).

    # Unmatched double rectangular closing brackets can be in a template or
    # tplarg, but unmatched double rectangular opening brackets cannot.
    # Unmatched double or triple closing braces inside a pair of
    # double rectangular brackets are treated as plain text.
    # Other formulation: in ambiguity between template or tplarg on one hand,
    # and a link on the other hand, the structure with the rightmost opening
    # takes precedence, even if this is the opening of a link without any
    # closing, so not producing an actual link.

    # In the case of more than three opening braces the last three are assumed
    # to belong to a tplarg, unless there is no matching triple of closing
    # braces, in which case the last two opening braces are are assumed to
    # belong to a template.

    # We must skip individual { like in:
    #   {{#ifeq: {{padleft:|1|}} | { | | &nbsp;}}
    # We must resolve ambiguities like this:
    #   {{{{ }}}} -> { {{{ }}} }
    #   {{{{{ }}}}} -> {{ {{{ }}} }}
    #   {{#if:{{{{{#if:{{{nominee|}}}|nominee|candidate}}|}}}|...}}

    # Handle:
    #   {{{{{|safesubst:}}}#Invoke:String|replace|{{{1|{{{{{|safesubst:}}}PAGENAME}}}}}|%s+%([^%(]-%)$||plain=false}}
    # as well as expressions with stray }:
    #   {{{link|{{ucfirst:{{{1}}}}}} interchange}}}

    if ldelim:  # 2-3
        re_open = re.compile('[{]{%d,}' % ldelim)  # at least ldelim
        re_next = re.compile('[{]{2,}|}{2,}')  # at least 2
    else:
        re_open = re.compile('{{2,}|\[{2,}')
        re_next = re.compile('{{2,}|}{2,}|\[{2,}|]{2,}')  # at least 2

    cur = 0
    while True:
        m1 = re_open.search(text, cur)
        if not m1:
            return
        lmatch = m1.end() - m1.start()
        if m1.group()[0] == '{':
            stack = [lmatch]  # stack of opening braces lengths
        else:
            stack = [-lmatch]  # negative means [
        end = m1.end()
        while True:
            m2 = re_next.search(text, end)
            if not m2:
                return  # unbalanced
            end = m2.end()
            brac = m2.group()[0]
            lmatch = m2.end() - m2.start()

            if brac == '{':
                stack.append(lmatch)
            elif brac == '}':
                while stack:
                    open_count = stack.pop()  # opening span
                    if open_count == 0:  # illegal unmatched [[
                        continue
                    if lmatch >= open_count:
                        lmatch -= open_count
                        if lmatch <= 1:  # either close or stray }
                            break
                    else:
                        # put back unmatched
                        stack.append(open_count - lmatch)
                        break
                if not stack:
                    yield m1.start(), end - lmatch
                    cur = end
                    break
                elif len(stack) == 1 and 0 < stack[0] < ldelim:
                    # ambiguous {{{{{ }}} }}
                    yield m1.start() + stack[0], end
                    cur = end
                    break
            elif brac == '[':  # [[
                stack.append(-lmatch)
            else:  # ]]
                while stack and stack[-1] < 0:  # matching [[
                    open_count = -stack.pop()
                    if lmatch >= open_count:
                        lmatch -= open_count
                        if lmatch <= 1:  # either close or stray ]
                            break
                    else:
                        # put back unmatched (negative)
                        stack.append(lmatch - open_count)
                        break
                if not stack:
                    yield m1.start(), end - lmatch
                    cur = end
                    break
                # unmatched ]] are discarded
                cur = end


def find_balanced(text, open_delim, close_delim):
    """
    Assuming that text contains a properly balanced expression using
    :param open_delim: as opening delimiters and
    :param close_delim: as closing delimiters.
    :return: an iterator producing pairs (start, end) of start and end
    positions in text containing a balanced expression.
    """
    open_pat = '|'.join([re.escape(x) for x in open_delim])
    # patter for delimiters expected after each opening delimiter
    after_pat = {o: re.compile(open_pat + '|' + c, re.DOTALL) for o, c in zip(open_delim, close_delim)}
    stack = []
    start = 0
    cur = 0
    start_set = False
    start_pat = re.compile(open_pat)
    next_pat = start_pat
    while True:
        next_match = next_pat.search(text, cur)
        if not next_match:
            return
        if not start_set:
            start = next_match.start()
            start_set = True
        delim = next_match.group(0)
        if delim in open_delim:
            stack.append(delim)
            next_pat = after_pat[delim]
        else:
            stack.pop()

            if stack:
                next_pat = after_pat[stack[-1]]
            else:
                yield start, next_match.end()
                next_pat = start_pat
                start = next_match.end()
                start_set = False
        cur = next_match.end()


# ----------------------------------------------------------------------
# Modules

# Only minimal support
# FIXME: import Lua modules.

modules = {
    'convert': {
        'convert': lambda x, u, *rest: x + ' ' + u,  # no conversion
    }
}


# ----------------------------------------------------------------------
# variables

class MagicWords(object):
    """
    One copy in each Extractor.

    @see https://doc.wikimedia.org/mediawiki-core/master/php/MagicWord_8php_source.html
    """
    names = [
        '!',
        'currentmonth',
        'currentmonth1',
        'currentmonthname',
        'currentmonthnamegen',
        'currentmonthabbrev',
        'currentday',
        'currentday2',
        'currentdayname',
        'currentyear',
        'currenttime',
        'currenthour',
        'localmonth',
        'localmonth1',
        'localmonthname',
        'localmonthnamegen',
        'localmonthabbrev',
        'localday',
        'localday2',
        'localdayname',
        'localyear',
        'localtime',
        'localhour',
        'numberofarticles',
        'numberoffiles',
        'numberofedits',
        'articlepath',
        'pageid',
        'sitename',
        'server',
        'servername',
        'scriptpath',
        'stylepath',
        'pagename',
        'pagenamee',
        'fullpagename',
        'fullpagenamee',
        'namespace',
        'namespacee',
        'namespacenumber',
        'currentweek',
        'currentdow',
        'localweek',
        'localdow',
        'revisionid',
        'revisionday',
        'revisionday2',
        'revisionmonth',
        'revisionmonth1',
        'revisionyear',
        'revisiontimestamp',
        'revisionuser',
        'revisionsize',
        'subpagename',
        'subpagenamee',
        'talkspace',
        'talkspacee',
        'subjectspace',
        'subjectspacee',
        'talkpagename',
        'talkpagenamee',
        'subjectpagename',
        'subjectpagenamee',
        'numberofusers',
        'numberofactiveusers',
        'numberofpages',
        'currentversion',
        'rootpagename',
        'rootpagenamee',
        'basepagename',
        'basepagenamee',
        'currenttimestamp',
        'localtimestamp',
        'directionmark',
        'contentlanguage',
        'numberofadmins',
        'cascadingsources',
    ]

    def __init__(self):
        self.values = {'!': '|'}

    def __getitem__(self, name):
        return self.values.get(name)

    def __setitem__(self, name, value):
        self.values[name] = value

    switches = [
        '__NOTOC__',
        '__FORCETOC__',
        '__TOC__',
        '__TOC__',
        '__NEWSECTIONLINK__',
        '__NONEWSECTIONLINK__',
        '__NOGALLERY__',
        '__HIDDENCAT__',
        '__NOCONTENTCONVERT__',
        '__NOCC__',
        '__NOTITLECONVERT__',
        '__NOTC__',
        '__START__',
        '__END__',
        '__INDEX__',
        '__NOINDEX__',
        '__STATICREDIRECT__',
        '__DISAMBIG__'
    ]


magicWordsRE = re.compile('|'.join(MagicWords.switches))


# ----------------------------------------------------------------------
# parser functions utilities

def ucfirst(string):
    """:return: a string with its first character uppercase"""
    if string:
        if len(string) > 1:
            return string[0].upper() + string[1:]
        else:
            return string.upper()
    else:
        return ''


def lcfirst(string):
    """:return: a string with its first character lowercase"""
    if string:
        if len(string) > 1:
            return string[0].lower() + string[1:]
        else:
            return string.lower()
    else:
        return ''


RE_TEMPLATE_TITLE = re.compile('([^:]*)(:.*)')

def fully_qualified_template_title(template_title):
    """
    Determine the namespace of the page being included through the template
    mechanism
    """
    if template_title.startswith(':'):
        # Leading colon by itself implies main namespace, so strip this colon
        return ucfirst(template_title[1:])
    else:
        m = RE_TEMPLATE_TITLE.match(template_title)
        if m:
            # colon found but not in the first position - check if it
            # designates a known namespace
            prefix = normalize_namespace(m.group(1))
            if prefix in knownNamespaces:
                return prefix + ucfirst(m.group(2))
    # The title of the page being included is NOT in the main namespace and
    # lacks any other explicit designation of the namespace - therefore, it
    # is resolved to the Template namespace (that's the default for the
    # template inclusion mechanism).

    # This is a defense against pages whose title only contains UTF-8 chars
    # that are reduced to an empty string. Right now I can think of one such
    # case - <C2><A0> which represents the non-breaking space.
    # In this particular case, this page is a redirect to [[Non-nreaking
    # space]], but having in the system a redirect page with an empty title
    # causes numerous problems, so we'll live happier without it.
    if template_title:
        return "Template:" + ucfirst(template_title)
    else:
        logging.warn("Skipping page with empty title")
        return ''


def normalize_namespace(ns):
    return ucfirst(ns)


# ----------------------------------------------------------------------
# Parser functions
# see http://www.mediawiki.org/wiki/Help:Extension:ParserFunctions
# https://github.com/Wikia/app/blob/dev/extensions/ParserFunctions/ParserFunctions_body.php

class Infix:
    """Infix operators.
    The calling sequence for the infix is:
      x |op| y
    """

    def __init__(self, function):
        self.function = function

    def __ror__(self, other):
        return Infix(lambda x, inner_self=self, inner_other=other: inner_self.function(inner_other, x))

    def __or__(self, other):
        return self.function(other)

    def __rlshift__(self, other):
        return Infix(lambda x, inner_self=self, inner_other=other: inner_self.function(inner_other, x))

    def __rshift__(self, other):
        return self.function(other)

    def __call__(self, value1, value2):
        return self.function(value1, value2)


ROUND = Infix(lambda x, y: round(x, y))


def sharp_expr(expr):
    # noinspection PyBroadException
    try:
        expr = re.sub('=', '==', expr)
        expr = re.sub('mod', '%', expr)
        expr = re.sub('\bdiv\b', '/', expr)
        expr = re.sub('\bround\b', '|ROUND|', expr)
        return text(eval(expr))
    except:
        return '<span class="error"></span>'


# noinspection PyUnusedLocal
def sharp_if(test_value, value_if_true, value_if_false=None, *args):
    # In theory, we should evaluate the first argument here,
    # but it was evaluated while evaluating part[0] in expandTemplate().
    if test_value.strip():
        # The {{#if:}} function is an if-then-else construct.
        # The applied condition is: "The condition string is non-empty".
        value_if_true = value_if_true.strip()
        if value_if_true:
            return value_if_true
    elif value_if_false:
        return value_if_false.strip()
    return ""


# noinspection PyUnusedLocal
def sharp_ifeq(lvalue, rvalue, value_if_true, value_if_false=None, *args):
    rvalue = rvalue.strip()
    if rvalue:
        # lvalue is always defined
        if lvalue.strip() == rvalue:
            # The {{#ifeq:}} function is an if-then-else construct. The
            # applied condition is "is rvalue equal to lvalue". Note that this
            # does only string comparison while MediaWiki implementation also
            # supports numerical comparissons.

            if value_if_true:
                return value_if_true.strip()
        else:
            if value_if_false:
                return value_if_false.strip()
    return ""


# noinspection PyUnusedLocal
def sharp_iferror(test, then='', else_=None, *args):
    if re.match('<(?:strong|span|p|div)\s(?:[^\s>]*\s+)*?class="(?:[^"\s>]*\s+)*?error(?:\s[^">]*)?"', test):
        return then
    elif else_ is None:
        return test.strip()
    else:
        return else_.strip()


def sharp_switch(primary, *params):
    # FIXME: we don't support numeric expressions in primary

    # {{#switch: comparison string
    #  | case1 = result1
    #  | case2
    #  | case4 = result2
    #  | 1 | case5 = result3
    #  | #default = result4
    # }}

    primary = primary.strip()
    found = False  # for fall through cases
    default = None
    rvalue = None
    lvalue = ''
    for param in params:
        # handle cases like:
        #  #default = [http://www.perseus.tufts.edu/hopper/text?doc=Perseus...]
        pair = param.split('=', 1)
        lvalue = pair[0].strip()
        rvalue = None
        if len(pair) > 1:
            # got "="
            rvalue = pair[1].strip()
            # check for any of multiple values pipe separated
            if found or primary in [v.strip() for v in lvalue.split('|')]:
                # Found a match, return now
                return rvalue
            elif lvalue == '#default':
                default = rvalue
            rvalue = None  # avoid defaulting to last case
        elif lvalue == primary:
            # If the value matches, set a flag and continue
            found = True
    # Default case
    # Check if the last item had no = sign, thus specifying the default case
    if rvalue is not None:
        return lvalue
    elif default is not None:
        return default
    return ''


# Extension Scribuntu
def sharp_invoke(module, function, frame):
    functions = modules.get(module)
    if functions:
        funct = functions.get(function)
        if funct:
            # find parameters in frame whose title is the one of the original
            # template invocation
            template_title = fully_qualified_template_title(function)
            pair = next((x for x in frame if x[0] == template_title), None)
            if pair:
                params = pair[1]
                # extract positional args
                params = [params.get(str(i + 1)) for i in range(len(params))]
                return funct(*params)
            else:
                return funct()
    return ''


parserFunctions = {

    '#expr': sharp_expr,

    '#if': sharp_if,

    '#ifeq': sharp_ifeq,

    '#iferror': sharp_iferror,

    '#ifexpr': lambda *args: '',  # not supported

    '#ifexist': lambda *args: '',  # not supported

    '#rel2abs': lambda *args: '',  # not supported

    '#switch': sharp_switch,

    '#language': lambda *args: '',  # not supported

    '#time': lambda *args: '',  # not supported

    '#timel': lambda *args: '',  # not supported

    '#titleparts': lambda *args: '',  # not supported

    # This function is used in some pages to construct links
    # http://meta.wikimedia.org/wiki/Help:URL
    'urlencode': lambda string, *rest: urllib.quote(string.encode('utf-8')),

    'lc': lambda string, *rest: string.lower() if string else '',

    'lcfirst': lambda string, *rest: lcfirst(string),

    'uc': lambda string, *rest: string.upper() if string else '',

    'ucfirst': lambda string, *rest: ucfirst(string),

    'int': lambda string, *rest: str(int(string)),

}


def call_parser_function(function_name, args, frame):
    """
    Parser functions have similar syntax as templates, except that
    the first argument is everything after the first colon.
    :return: the result of the invocation, None in case of failure.

    http://meta.wikimedia.org/wiki/Help:ParserFunctions
    """

    # noinspection PyBroadException
    try:
        if function_name == '#invoke':
            # special handling of frame
            ret = sharp_invoke(args[0].strip(), args[1].strip(), frame)
            logging.debug('parserFunction> %s %s', function_name, ret)
            return ret
        if function_name in parserFunctions:
            ret = parserFunctions[function_name](*args)
            logging.debug('parserFunction> %s %s', function_name, ret)
            return ret
    except:
        return ""  # FIXME: fix errors

    return ""


# ----------------------------------------------------------------------
# Expand using WikiMedia API
# import json

# def expandTemplates(text):
#     """Expand templates invoking MediaWiki API"""
#     text = urlib.urlencodew(text.encode('utf-8'))
#     base = urlbase[:urlbase.rfind('/')]
#     url = base + "/w/api.php?action=expandtemplates&format=json&text=" + text
#     exp = json.loads(urllib.urlopen(url))
#     return exp['expandtemplates']['*']

# ----------------------------------------------------------------------
# Extract Template definition

reNoinclude = re.compile(r'<noinclude>(?:.*?)</noinclude>', re.DOTALL)
reIncludeonly = re.compile(r'<includeonly>|</includeonly>', re.DOTALL)

templates = {}
redirects = {}
# cache of parser templates
templateCache = {}


def define_template(title, page):
    """
    Adds a template defined in the :param page:.
    @see https://en.wikipedia.org/wiki/Help:Template#Noinclude.2C_includeonly.2C_and_onlyinclude
    """
    global templates
    global redirects

    # title = normalizeTitle(title)

    # check for redirects
    m = re.match('#REDIRECT.*?\[\[([^\]]*)]]', page[0])
    if m:
        redirects[title] = m.group(1)  # normalizeTitle(m.group(1))
        return

    text = unescape(''.join(page))

    # We're storing template text for future inclusion, therefore,
    # remove all <noinclude> text and keep all <includeonly> text
    # (but eliminate <includeonly> tags per se).
    # However, if <onlyinclude> ... </onlyinclude> parts are present,
    # then only keep them and discard the rest of the template body.
    # This is because using <onlyinclude> on a text fragment is
    # equivalent to enclosing it in <includeonly> tags **AND**
    # enclosing all the rest of the template body in <noinclude> tags.

    # remove comments
    text = comment.sub('', text)

    # eliminate <noinclude> fragments
    text = reNoinclude.sub('', text)
    # eliminate unterminated <noinclude> elements
    text = re.sub(r'<noinclude\s*>.*$', '', text, flags=re.DOTALL)
    text = re.sub(r'<noinclude/>', '', text)

    only_include_accumulator = ''
    for m in re.finditer('<onlyinclude>(.*?)</onlyinclude>', text, re.DOTALL):
        only_include_accumulator += m.group(1)
    if only_include_accumulator:
        text = only_include_accumulator
    else:
        text = reIncludeonly.sub('', text)

    if text:
        if title in templates:
            logging.warn('Redefining: %s', title)
        templates[title] = text


# ----------------------------------------------------------------------

def drop_nested(text, open_delim, close_delim):
    """
    A matching function for nested expressions, e.g. namespaces and tables.
    """
    open_re = re.compile(open_delim)
    close_re = re.compile(close_delim)
    # partition text in separate blocks { } { }
    spans = []  # pairs (s, e) for each partition
    nest = 0  # nesting level
    start = open_re.search(text, 0)
    if not start:
        return text
    end = close_re.search(text, start.end())
    next_match = start
    while end:
        # noinspection PyUnresolvedReferences
        next_match = open_re.search(text, next_match.end())
        if not next_match:  # termination
            while nest:  # close all pending
                nest -= 1
                # noinspection PyUnresolvedReferences
                end0 = close_re.search(text, end.end())
                if end0:
                    end = end0
                else:
                    break
            spans.append((start.start(), end.end()))
            break
        while end.end() < next_match.start():
            # { } {
            if nest:
                nest -= 1
                # try closing more
                last = end.end()
                end = close_re.search(text, end.end())
                if not end:  # unbalanced
                    if spans:
                        span = (spans[0][0], last)
                    else:
                        span = (start.start(), last)
                    spans = [span]
                    break
            else:
                spans.append((start.start(), end.end()))
                # advance start, find next_match close
                start = next_match
                end = close_re.search(text, next_match.end())
                break  # { }
        if next_match != start:
            # { { }
            nest += 1
    # collect text outside partitions
    return drop_spans(spans, text)


def drop_spans(spans, text):
    """
    Drop from text the blocks identified in :param spans:, possibly nested.
    """
    spans.sort()
    res = ''
    offset = 0
    for s, e in spans:
        if offset <= s:  # handle nesting
            if offset < s:
                res += text[offset:s]
            offset = e
    res += text[offset:]
    return res


# ----------------------------------------------------------------------
# WikiLinks
# See https://www.mediawiki.org/wiki/Help:Links#Internal_links

# Can be nested [[File:..|..[[..]]..|..]], [[Category:...]], etc.
# Also: [[Help:IPA for Catalan|[andora]]]

def replace_internal_links(text):
    """
    Replaces external links of the form:
    [[title |...|label]]trail

    with title concatenated with trail, when present, e.g. 's' for plural.
    """
    # call this after removal of external links, so we need not worry about
    # triple closing ]]].
    cur = 0
    res = ''
    for s, e in find_balanced(text, ['[['], [']]']):
        m = tailRE.match(text, e)
        if m:
            trail = m.group(0)
            end = m.end()
        else:
            trail = ''
            end = e
        inner = text[s + 2:e - 2]
        # find first |
        pipe = inner.find('|')
        if pipe < 0:
            title = inner
            label = title
        else:
            title = inner[:pipe].rstrip()
            # find last |
            curp = pipe + 1
            for s1, e1 in find_balanced(inner, ['[['], [']]']):
                last = inner.rfind('|', curp, s1)
                if last >= 0:
                    pipe = last  # advance
                curp = e1
            label = inner[pipe + 1:].strip()
        res += text[cur:s] + make_internal_link(title, label) + trail
        cur = end
    return res + text[cur:]


# the official version is a method in class Parser, similar to this:
# def replaceInternalLinks2(text):
#     global wgExtraInterlanguageLinkPrefixes

#     # the % is needed to support urlencoded titles as well
#     tc = Title::legalChars() + '#%'
#     # Match a link having the form [[namespace:link|alternate]]trail
#     e1 = re.compile("([%s]+)(?:\\|(.+?))?]](.*)" % tc, re.S | re.D)
#     # Match cases where there is no "]]", which might still be images
#     e1_img = re.compile("([%s]+)\\|(.*)" % tc, re.S | re.D)

#     holders = LinkHolderArray(self)

#     # split the entire text string on occurrences of [[
#     iterBrackets = re.compile('[[').finditer(text)

#     m in iterBrackets.next()
#     # get the first element (all text up to first [[)
#     s = text[:m.start()]
#     cur = m.end()

#     line = s

#     useLinkPrefixExtension = self.getTargetLanguage().linkPrefixExtension()
#     e2 = None
#     if useLinkPrefixExtension:
#         # Match the end of a line for a word that is not followed by whitespace,
#         # e.g. in the case of "The Arab al[[Razi]]",  "al" will be matched
#         global wgContLang
#         charset = wgContLang.linkPrefixCharset()
#         e2 = re.compile("((?>.*[^charset]|))(.+)", re.S | re.D | re.U)

#     if self.mTitle is None:
#         raise MWException(__METHOD__ + ": \self.mTitle is null\n")

#     nottalk = not self.mTitle.isTalkPage()

#     if useLinkPrefixExtension:
#         m = e2.match(s)
#         if m:
#             first_prefix = m.group(2)
#         else:
#             first_prefix = false
#     else:
#         prefix = ''

#     useSubpages = self.areSubpagesAllowed()

#     for m in iterBrackets:
#         line = text[cur:m.start()]
#         cur = m.end()

#         # TODO: Check for excessive memory usage

#         if useLinkPrefixExtension:
#             m = e2.match(e2)
#             if m:
#                 prefix = m.group(2)
#                 s = m.group(1)
#             else:
#                 prefix = ''
#             # first link
#             if first_prefix:
#                 prefix = first_prefix
#                 first_prefix = False

#         might_be_img = False

#         m = e1.match(line)
#         if m: # page with normal label or alt
#             label = m.group(2)
#             # If we get a ] at the beginning of m.group(3) that means we have a link that is something like:
#             # [[Image:Foo.jpg|[http://example.com desc]]] <- having three ] in a row fucks up,
#             # the real problem is with the e1 regex
#             # See bug 1300.
#             #
#             # Still some problems for cases where the ] is meant to be outside punctuation,
#             # and no image is in sight. See bug 2095.
#             #
#             if label and m.group(3)[0] == ']' and '[' in label:
#                 label += ']' # so that replaceExternalLinks(label) works later
#                 m.group(3) = m.group(3)[1:]
#             # fix up urlencoded title texts
#             if '%' in m.group(1):
#                 # Should anchors '#' also be rejected?
#                 m.group(1) = str_replace(array('<', '>'), array('&lt', '&gt'), rawurldecode(m.group(1)))
#             trail = m.group(3)
#         else:
#             m = e1_img.match(line):
#             if m:
#                 # Invalid, but might be an image with a link in its caption
#                 might_be_img = true
#                 label = m.group(2)
#                 if '%' in m.group(1):
#                     m.group(1) = rawurldecode(m.group(1))
#                 trail = ""
#             else:		# Invalid form; output directly
#                 s += prefix + '[[' + line
#                 continue

#         origLink = m.group(1)

#         # Dont allow internal links to pages containing
#         # PROTO: where PROTO is a valid URL protocol these
#         # should be external links.
#         if (preg_match('/^(?i:' + self.mUrlProtocols + ')/', origLink)) {
#             s += prefix + '[[' + line
#             continue
#         }

#         # Make subpage if necessary
#         if useSubpages:
#             link = self.maybeDoSubpageLink(origLink, label)
#         else:
#             link = origLink

#         noforce = origLink[0] != ':'
#         if not noforce:
#             # Strip off leading ':'
#             link = link[1:]

#         nt = Title::newFromText(self.mStripState.unstripNoWiki(link))
#         if nt is None:
#             s += prefix + '[[' + line
#             continue

#         ns = nt.getNamespace()
#         iw = nt.getInterwiki()

#         if might_be_img {	# if this is actually an invalid link
#             if (ns == NS_FILE and noforce) { # but might be an image
#                 found = False
#                 while True:
#                     # look at the next 'line' to see if we can close it there
#                     next_line = iterBrakets.next()
#                     if not next_line:
#                         break
#                     m = explode(']]', next_line, 3)
#                     if m.lastindex == 3:
#                         # the first ]] closes the inner link, the second the image
#                         found = True
#                         label += "[[%s]]%s" % (m.group(0), m.group(1))
#                         trail = m.group(2)
#                         break
#                     elif m.lastindex == 2:
#                         # if there is exactly one ]] that is fine, we will keep looking
#                         label += "[[{m[0]}]]{m.group(1)}"
#                     else:
#                         # if next_line is invalid too, we need look no further
#                         label += '[[' + next_line
#                         break
#                 if not found:
#                     # we couldnt find the end of this imageLink, so output it raw
#                     # but dont ignore what might be perfectly normal links in the text we ve examined
#                     holders.merge(self.replaceInternalLinks2(label))
#                     s += "{prefix}[[%s|%s" % (link, text)
#                     # note: no trail, because without an end, there *is* no trail
#                     continue
#             } else: # it is not an image, so output it raw
#                 s += "{prefix}[[%s|%s" % (link, text)
#                 # note: no trail, because without an end, there *is* no trail
#                      continue
#         }

#         wasblank = (text == '')
#         if wasblank:
#             text = link
#         else:
#             # Bug 4598 madness.  Handle the quotes only if they come from the alternate part
#             # [[Lista d''e paise d''o munno]] . <a href="...">Lista d''e paise d''o munno</a>
#             # [[Criticism of Harry Potter|Criticism of ''Harry Potter'']]
#             #    . <a href="Criticism of Harry Potter">Criticism of <i>Harry Potter</i></a>
#             text = self.doQuotes(text)

#         # Link not escaped by : , create the various objects
#         if noforce and not nt.wasLocalInterwiki():
#             # Interwikis
#             if iw and mOptions.getInterwikiMagic() and nottalk and (
#                     Language::fetchLanguageName(iw, None, 'mw') or
#                     in_array(iw, wgExtraInterlanguageLinkPrefixes)):
#                 # Bug 24502: filter duplicates
#                 if iw not in mLangLinkLanguages:
#                     self.mLangLinkLanguages[iw] = True
#                     self.mOutput.addLanguageLink(nt.getFullText())

#                 s = rstrip(s + prefix)
#                 s += strip(trail, "\n") == '' ? '': prefix + trail
#                 continue

#             if ns == NS_FILE:
#                 if not wfIsBadImage(nt.getDBkey(), self.mTitle):
#                     if wasblank:
#                         # if no parameters were passed, text
#                         # becomes something like "File:Foo.png",
#                         # which we dont want to pass on to the
#                         # image generator
#                         text = ''
#                     else:
#                         # recursively parse links inside the image caption
#                         # actually, this will parse them in any other parameters, too,
#                         # but it might be hard to fix that, and it doesnt matter ATM
#                         text = self.replaceExternalLinks(text)
#                         holders.merge(self.replaceInternalLinks2(text))
#                     # cloak any absolute URLs inside the image markup, so replaceExternalLinks() wont touch them
#                     s += prefix + self.armorLinks(
#                         self.makeImage(nt, text, holders)) + trail
#                 else:
#                     s += prefix + trail
#                 continue

#             if ns == NS_CATEGORY:
#                 s = rstrip(s + "\n") # bug 87

#                 if wasblank:
#                     sortkey = self.getDefaultSort()
#                 else:
#                     sortkey = text
#                 sortkey = Sanitizer::decodeCharReferences(sortkey)
#                 sortkey = str_replace("\n", '', sortkey)
#                 sortkey = self.getConverterLanguage().convertCategoryKey(sortkey)
#                 self.mOutput.addCategory(nt.getDBkey(), sortkey)

#                 s += strip(prefix + trail, "\n") == '' ? '' : prefix + trail

#                 continue
#             }
#         }

#         # Self-link checking. For some languages, variants of the title are checked in
#         # LinkHolderArray::doVariants() to allow batching the existence checks necessary
#         # for linking to a different variant.
#         if ns != NS_SPECIAL and nt.equals(self.mTitle) and !nt.hasFragment():
#             s += prefix + Linker::makeSelfLinkObj(nt, text, '', trail)
#                  continue

#         # NS_MEDIA is a pseudo-namespace for linking directly to a file
#         # @todo FIXME: Should do batch file existence checks, see comment below
#         if ns == NS_MEDIA:
#             # Give extensions a chance to select the file revision for us
#             options = []
#             descQuery = False
#             Hooks::run('BeforeParserFetchFileAndTitle',
#                        [this, nt, &options, &descQuery])
#             # Fetch and register the file (file title may be different via hooks)
#             file, nt = self.fetchFileAndTitle(nt, options)
#             # Cloak with NOPARSE to avoid replacement in replaceExternalLinks
#             s += prefix + self.armorLinks(
#                 Linker::makeMediaLinkFile(nt, file, text)) + trail
#             continue

#         # Some titles, such as valid special pages or files in foreign repos, should
#         # be shown as bluelinks even though they are not included in the page table
#         #
#         # @todo FIXME: isAlwaysKnown() can be expensive for file links; we should really do
#         # batch file existence checks for NS_FILE and NS_MEDIA
#         if iw == '' and nt.isAlwaysKnown():
#             self.mOutput.addLink(nt)
#             s += self.makeKnownLinkHolder(nt, text, array(), trail, prefix)
#         else:
#             # Links will be added to the output link list after checking
#             s += holders.makeHolder(nt, text, array(), trail, prefix)
#     }
#     return holders

def make_internal_link(title, label):
    colon = title.find(':')
    if colon > 0 and title[:colon] not in acceptedNamespaces:
        return ''
    if colon == 0:
        # drop also :File:
        colon2 = title.find(':', colon + 1)
        if colon2 > 1 and title[colon + 1:colon2] not in acceptedNamespaces:
            return ''
    if Extractor.keepLinks:
        # fixed original code. Is label the url here?
        return '<a href="%s">%s</a>' % (urllib.quote(title.encode('utf-8')), label)
    else:
        return label


# ----------------------------------------------------------------------
# External links

# from: https://doc.wikimedia.org/mediawiki-core/master/php/DefaultSettings_8php_source.html

wgUrlProtocols = [
    'bitcoin:', 'ftp://', 'ftps://', 'geo:', 'git://', 'gopher://', 'http://',
    'https://', 'irc://', 'ircs://', 'magnet:', 'mailto:', 'mms://', 'news:',
    'nntp://', 'redis://', 'sftp://', 'sip:', 'sips:', 'sms:', 'ssh://',
    'svn://', 'tel:', 'telnet://', 'urn:', 'worldwind://', 'xmpp:', '//'
]

# from: https://doc.wikimedia.org/mediawiki-core/master/php/Parser_8php_source.html

# Constants needed for external link processing
# Everything except bracket, space, or control characters
# \p{Zs} is unicode 'separator, space' category. It covers the space 0x20
# as well as U+3000 is IDEOGRAPHIC SPACE for bug 19052
EXT_LINK_URL_CLASS = r'[^][<>"\x00-\x20\x7F\s]'
ExtLinkBracketedRegex = re.compile(
    '\[(((?i)' + '|'.join(wgUrlProtocols) + ')' + EXT_LINK_URL_CLASS + r'+)\s*([^\]\x00-\x08\x0a-\x1F]*?)\]',
    re.S | re.U)
EXT_IMAGE_REGEX = re.compile(
    r"""^(http://|https://)([^][<>"\x00-\x20\x7F\s]+)
    /([A-Za-z0-9_.,~%\-+&;#*?!=()@\x80-\xFF]+)\.((?i)gif|png|jpg|jpeg)$""",
    re.X | re.S | re.U)


def replace_external_links(text):
    s = ''
    cur = 0
    for m in ExtLinkBracketedRegex.finditer(text):
        s += text[cur:m.start()]
        cur = m.end()

        url = m.group(1)
        label = m.group(3)

        # # The characters '<' and '>' (which were escaped by
        # # removeHTMLtags()) should not be included in
        # # URLs, per RFC 2396.
        # m2 = re.search('&(lt|gt);', url)
        # if m2:
        #     link = url[m2.end():] + ' ' + link
        #     url = url[0:m2.end()]

        # If the link text is an image URL, replace it with an <img> tag
        # This happened by accident in the original parser, but some people used it extensively
        m = EXT_IMAGE_REGEX.match(label)
        if m:
            label = make_external_image(label)

        # Use the encoded URL
        # This means that users can paste URLs directly into the text
        # Funny characters like ö aren't valid in URLs anyway
        # This was changed in August 2004
        s += make_external_link(url, label)  # + trail

    return s + text[cur:]


# Function applied to wikiLinks
def make_external_link(title, anchor):
    colon = title.find(':')
    if colon > 0 and title[:colon] not in acceptedNamespaces:
        return ''
    if colon == 0:
        # drop also :File:
        colon2 = title.find(':', colon + 1)
        if colon2 > 1 and title[colon + 1:colon2] not in acceptedNamespaces:
            return ''
    if Extractor.keepLinks:
        return '<a href="%s">%s</a>' % (urllib.quote(title.encode('utf-8')), anchor)
    else:
        return anchor


def make_external_image(url, alt=''):
    if Extractor.keepLinks:
        return '<img src="%s" alt="%s">' % (url, alt)
    else:
        return alt


# ----------------------------------------------------------------------

# match tail after wikilink
tailRE = re.compile('\w+')

syntaxhighlight = re.compile('&lt;syntaxhighlight .*?&gt;(.*?)&lt;/syntaxhighlight&gt;', re.DOTALL)

expand_templates = True


def clean(extractor, text):
    """
    Transforms wiki markup.
    @see https://www.mediawiki.org/wiki/Help:Formatting
    """

    if expand_templates:
        # expand templates
        # See: http://www.mediawiki.org/wiki/Help:Templates
        text = extractor.expand_templates(text)
    else:
        # Drop transclusions (template, parser functions)
        text = drop_nested(text, r'{{', r'}}')

    # Drop tables
    text = drop_nested(text, r'{\|', r'\|}')

    # replace external links
    text = replace_external_links(text)

    # replace internal links
    text = replace_internal_links(text)

    # drop MagicWords behavioral switches
    text = magicWordsRE.sub('', text)

    # Process HTML

    # turn into HTML, except for the content of <syntaxhighlight>
    res = ''
    cur = 0
    for m in syntaxhighlight.finditer(text):
        end = m.end()
        res += unescape(text[cur:m.start()]) + m.group(1)
        cur = end
    text = res + unescape(text[cur:])

    # Handle bold/italic/quote
    if extractor.toHTML:
        text = bold_italic.sub(r'<b>\1</b>', text)
        text = bold.sub(r'<b>\1</b>', text)
        text = italic.sub(r'<i>\1</i>', text)
    else:
        text = bold_italic.sub(r'\1', text)
        text = bold.sub(r'\1', text)
        text = italic_quote.sub(r'"\1"', text)
        text = italic.sub(r'"\1"', text)
        text = quote_quote.sub(r'"\1"', text)
    # residuals of unbalanced quotes
    text = text.replace("'''", '').replace("''", '"')

    # Collect spans

    spans = []
    # Drop HTML comments
    for m in comment.finditer(text):
        spans.append((m.start(), m.end()))

    # Drop self-closing tags
    for pattern in selfClosing_tag_patterns:
        for m in pattern.finditer(text):
            spans.append((m.start(), m.end()))

    # Drop ignored tags
    for left, right in ignored_tag_patterns:
        for m in left.finditer(text):
            spans.append((m.start(), m.end()))
        for m in right.finditer(text):
            spans.append((m.start(), m.end()))

    # Bulk remove all spans
    text = drop_spans(spans, text)

    # Drop discarded elements
    for elt_tag in discardElements:
        text = drop_nested(text, r'<\s*%s\b[^>/]*>' % elt_tag, r'<\s*/\s*%s>' % elt_tag)

    if not extractor.toHTML:
        # Turn into text what is left (&amp;nbsp;) and <syntaxhighlight>
        text = unescape(text)

    # Expand placeholders
    for pattern, placeholder in placeholder_tag_patterns:
        index = 1
        for match in pattern.finditer(text):
            text = text.replace(match.group(), '%s_%d' % (placeholder, index))
            index += 1

    text = text.replace('<<', u'«').replace('>>', u'»')

    #############################################

    # Cleanup text
    text = text.replace('\t', ' ')
    text = spaces.sub(' ', text)
    text = dots.sub('...', text)
    text = re.sub(u' (,:\.\)\]»)', r'\1', text)
    text = re.sub(u'(\[\(«) ', r'\1', text)
    text = re.sub(r'\n\W+?\n', '\n', text, flags=re.U)  # lines with only punctuations
    text = text.replace(',,', ',').replace(',.', '.')

    return text


# skip level 1, it is page name level
section = re.compile(r'(==+)\s*(.*?)\s*\1')

listOpen = {'*': '<ul>', '#': '<ol>', ';': '<dl>', ':': '<dl>'}
listClose = {'*': '</ul>', '#': '</ol>', ';': '</dl>', ':': '</dl>'}
listItem = {'*': '<li>%s</li>', '#': '<li>%s</<li>', ';': '<dt>%s</dt>',
            ':': '<dd>%s</dd>'}


def compact(text):
    """
    Deal with headers, lists, empty sections, residuals of tables.
    """

    page = []  # list of paragraph
    headers = {}  # Headers for unfilled sections
    empty_section = False  # empty sections are discarded
    list_level = ''  # nesting of lists

    for line in text.split('\n'):

        if not line:
            continue
        # Handle section titles
        m = section.match(line)
        if m:
            title = m.group(2)
            lev = len(m.group(1))
            if Extractor.toHTML:
                page.append("<h%d>%s</h%d>" % (lev, title, lev))
            if title and title[-1] not in '!?':
                title += '.'
            headers[lev] = title
            # drop previous headers
            for i in list(headers.keys()):
                if i > lev:
                    del headers[i]
            empty_section = True
            continue
        # Handle page title
        if line.startswith('++'):
            title = line[2:-2]
            if title:
                if title[-1] not in '!?':
                    title += '.'
                page.append(title)
        # handle indents
        elif line[0] == ':':
            # page.append(line.lstrip(':*#;'))
            continue
        # handle lists
        elif line[0] in '*#;:':
            if Extractor.toHTML:
                i = 0
                for c, n in zip_longest(list_level, line):
                    if n not in '*#;:':
                        if c:
                            page.append(listClose[c])
                            list_level = list_level[:-1]
                            continue
                        else:
                            break
                    if c != n and (not c or (c not in ';:' and n not in ';:')):
                        if c:
                            # close level
                            page.append(listClose[c])
                            list_level = list_level[:-1]
                        list_level = list_level + n
                        page.append(listOpen[n])
                    i += 1
                n = line[i - 1]
                line = line[i:].strip()
                if line:
                    page.append(listItem[n] % line)
            else:
                continue
        elif len(list_level):
            for c in reversed(list_level):
                page.append(listClose[c])
            list_level = []

        # Drop residuals of lists
        elif line[0] in '{|' or line[-1] == '}':
            continue
        # Drop irrelevant lines
        elif (line[0] == '(' and line[-1] == ')') or line.strip('.-') == '':
            continue
        elif len(headers):
            if not Extractor.keepSections:
                items = list(headers.items())
                items.sort()
                for (i, v) in items:
                    page.append(v)
            headers.clear()
            page.append(line)  # first line
            empty_section = False
        elif not empty_section:
            page.append(line)
            # dangerous
            # # Drop preformatted
            # elif line[0] == ' ':
            #     continue

    return page


def handle_unicode(entity):
    numeric_code = int(entity[2:-1])

    if numeric_code >= 0x10000:
        return ''

    return chr(numeric_code)


# ------------------------------------------------------------------------------
# Output

class NextFile(object):
    """
    Synchronous generation of next available file name.
    """

    filesPerDir = 100

    def __init__(self, lock, path_name):
        self.lock = lock
        self.path_name = path_name
        self.dir_index = -1
        self.file_index = -1

    def next(self):
        with self.lock:
            self.file_index = (self.file_index + 1) % NextFile.filesPerDir
            if self.file_index == 0:
                self.dir_index += 1
            dirname = self._dirname()
            if not os.path.isdir(dirname):
                os.makedirs(dirname)
            return self._filepath()

    def _dirname(self):
        char1 = self.dir_index % 26
        char2 = self.dir_index / 26 % 26
        return os.path.join(self.path_name, '%c%c' % (ord('A') + char2, ord('A') + char1))

    def _filepath(self):
        return '%s/wiki_%02d' % (self._dirname(), self.file_index)


class OutputSplitter(object):
    """
    File-like object, that splits output to multiple files of a given max size.
    """

    def __init__(self, next_file, max_file_size=0, compress=True):
        """
        :param next_file: a NextFile object from which to obtain filenames
            to use.
        :param max_file_size: the maximum size of each file.
        :para compress: whether to write data with bzip compression.
        """
        self.nextFile = next_file
        self.compress = compress
        self.max_file_size = max_file_size
        self.file = self.open(self.nextFile.next())

    def reserve(self, size):
        if self.file.tell() + size > self.max_file_size:
            self.close()
            self.file = self.open(self.nextFile.next())

    def write(self, data):
        self.file.write(data)

    def close(self):
        self.file.close()

    def open(self, filename):
        if self.compress:
            return bz2.BZ2File(filename + '.bz2', 'w')
        else:
            return open(filename, 'w')


# ----------------------------------------------------------------------
# READER

tagRE = re.compile(r'(.*?)<(/?\w+)[^>]*>(?:([^<]*)(<.*?>)?)?')


#                    1     2               3      4
# tagRE = re.compile(r'(.*?)<(/?\w+)[^>]*>([^<]*)')

def load_templates(input_file, output_file=None):
    """
    Load templates from :param input_file:.
    :param output_file: input_file where to save templates.
    """
    template_prefix = templateNamespace + ':'
    articles = 0
    page = []
    in_text = False
    if output_file:
        output = io.open(output_file, mode='w', encoding='utf-8')
    for line in input_file:
        line = line.decode('utf-8')
        if '<' not in line:  # faster than doing re.search()
            if in_text:
                page.append(line)
            continue
        m = tagRE.search(line)
        if not m:
            continue
        elt_tag = m.group(2)
        if elt_tag == 'page':
            page = []
        elif elt_tag == 'title':
            title = m.group(3)
        elif elt_tag == 'text':
            in_text = True
            line = line[m.start(3):m.end(3)]
            page.append(line)
            if m.lastindex == 4:  # open-close
                in_text = False
        elif elt_tag == '/text':
            if m.group(1):
                page.append(m.group(1))
            in_text = False
        elif in_text:
            page.append(line)
        elif elt_tag == '/page':
            if title.startswith(template_prefix):
                define_template(title, page)
                if output_file:
                    output.write('<page>\n')
                    output.write('   <title>%s</title>\n' % title)
                    output.write('   <ns>10</ns>\n')
                    output.write('   <text>')
                    # noinspection PyAssignmentToLoopOrWithParameter
                    for line in page:
                        output.write(line)
                    output.write('   </text>\n')
                    output.write('</page>\n')
            page = []
            articles += 1
            if articles % 10000 == 0:
                logging.info("Preprocessed %d pages", articles)


def process_dump(input_fn, template_file, outdir, file_size, file_compress, threads):
    """
    :param input_fn: name of the wikipedia dump f.
    :param template_file: optional f with template definitions.
    :param outdir: name of the directory where to store extracted files.
    :param file_size: max size of each extracted f.
    :param file_compress: whether to compress files with bzip.
    """
    global urlbase
    global knownNamespaces
    global templateNamespace
    global expand_templates

    if input_fn.lower().endswith("bz2"):
        opener = bz2.BZ2File
    else:
        opener = open

    input_file = opener(input_fn)

    # collect siteinfo
    for line in input_file:
        line = line.decode('utf-8')
        m = tagRE.search(line)
        if not m:
            continue
        elt_tag = m.group(2)
        if elt_tag == 'base':
            # discover urlbase from the xml dump f
            # /mediawiki/siteinfo/base
            base = m.group(3)
            urlbase = base[:base.rfind("/")]
        elif elt_tag == 'namespace':
            knownNamespaces.add(m.group(3))
            if re.search('key="10"', line):
                templateNamespace = m.group(3)
        elif elt_tag == '/siteinfo':
            break

    if expand_templates:
        # preprocess
        logging.info("Preprocessing dump to collect template definitions: this may take some time.")
        if template_file and os.path.exists(template_file):
            input_file.close()
            with open(template_file) as f:
                load_templates(f)
        else:
            load_templates(input_file, template_file)
            input_file.close()
        input_file = opener(input_fn)

    # process pages
    logging.info("Starting processing pages from %s.", input_fn)

    # initialize jobs queue
    # threads = multiprocessing.cpu_count()
    logging.info("Using %d CPUs.", threads)
    queue = Queue.Queue(maxsize=2 * threads)
    lock = threading.Lock()  # for protecting shared state.

    next_file = NextFile(lock, outdir)

    # start worker threads
    workers = []
    for _ in xrange(max(1, threads - 1)):  # keep one for master
        output_splitter = OutputSplitter(next_file, file_size, file_compress)
        extractor = ExtractorThread(queue, output_splitter)
        workers.append(extractor)

    # we collect indivual lines, since str.join() is significantly faster than
    # concatenation
    page = []
    page_id = None
    in_text = False
    redirect = False
    for line in input_file:
        line = line.decode('utf-8')
        if '<' not in line:  # faster than doing re.search()
            if in_text:
                page.append(line)
            continue
        m = tagRE.search(line)
        if not m:
            continue
        elt_tag = m.group(2)
        if elt_tag == 'page':
            page = []
            redirect = False
        elif elt_tag == 'id' and not page_id:
            page_id = m.group(3)
        elif elt_tag == 'title':
            title = m.group(3)
        elif elt_tag == 'redirect':
            redirect = True
        elif elt_tag == 'text':
            in_text = True
            line = line[m.start(3):m.end(3)]
            page.append(line)
            if m.lastindex == 4:  # open-close
                in_text = False
        elif elt_tag == '/text':
            if m.group(1):
                page.append(m.group(1))
            in_text = False
        elif in_text:
            page.append(line)
        elif elt_tag == '/page':
            colon = title.find(':')
            if (colon < 0 or title[:colon] in acceptedNamespaces) and \
                    not redirect and not title.startswith(templateNamespace):
                queue.put(Extractor(page_id, title, page), True)  # block if full
            page_id = None
            page = []

    # wait for empty queue
    queue.join()

    input_file.close()


# ----------------------------------------------------------------------
# Multithread version

class ExtractorThread(threading.Thread):
    """
    Extractor thread.
    """

    def __init__(self, queue, splitter):
        self._queue = queue
        self._splitter = splitter
        threading.Thread.__init__(self)
        self.setDaemon(True)  # let the process die when main thread is killed
        self.start()

    def run(self):
        while True:
            job = self._queue.get()
            if job:
                job.extract(self._splitter)
                self._queue.task_done()
            else:
                break


# ----------------------------------------------------------------------

# Minimum size of output files
minFileSize = 200 * 1024


def main():
    global urlbase, acceptedNamespaces
    global expand_templates

    parser = argparse.ArgumentParser(prog=os.path.basename(sys.argv[0]),
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=__doc__)
    parser.add_argument("input",
                        help="XML wiki dump file")
    group_o = parser.add_argument_group('Output')
    group_o.add_argument("-o", "--output", default="text",
                         help="output directory")
    group_o.add_argument("-b", "--bytes", default="1M",
                         help="put specified bytes per output file (default is %(default)s)", metavar="n[KMG]")
    group_o.add_argument("-c", "--compress", action="store_true",
                         help="compress output files using bzip")

    group_p = parser.add_argument_group('Processing')
    group_p.add_argument("--html", action="store_true",
                         help="produce HTML output, subsumes --links and --sections")
    group_p.add_argument("-l", "--links", action="store_true",
                         help="preserve links")
    group_p.add_argument("-ns", "--namespaces", default="", metavar="ns1,ns2",
                         help="accepted namespaces")
    group_p.add_argument("-s", "--sections", action="store_true",
                         help="preserve sections")
    group_p.add_argument("--templates",
                         help="use or create file containing templates")
    group_p.add_argument("--no-templates", action="store_false",
                         help="Do not expand templates")
    parser.add_argument("--threads", type=int, default=2,
                        help="Number of threads to use (default 2)")

    group_s = parser.add_argument_group('Special')
    group_s.add_argument("-q", "--quiet", action="store_true",
                         help="suppress reporting progress info")
    group_s.add_argument("--debug", action="store_true",
                         help="print debug info")
    group_s.add_argument("-a", "--article", action="store_true",
                         help="analyze a file containing a single article (debug) option")
    group_s.add_argument("-v", "--version", action="version",
                         version='%(prog)s ' + version,
                         help="print program version")

    args = parser.parse_args()

    Extractor.keepLinks = args.links
    Extractor.keepSections = args.sections
    Extractor.toHTML = args.html
    if args.html:
        Extractor.keepLinks = True
        Extractor.keepSections = True

    expand_templates = args.no_templates

    try:
        power = 'kmg'.find(args.bytes[-1].lower()) + 1
        file_size = int(args.bytes[:-1]) * 1024 ** power
        if file_size < minFileSize:
            raise ValueError()
    except ValueError:
        logging.error('Insufficient or invalid size: %s', args.bytes)
        return

    if args.namespaces:
        acceptedNamespaces = set(args.ns.split(','))

    logging_format = '%(levelname)s: %(message)s'
    logging.basicConfig(format=logging_format)

    logger = logging.getLogger()
    if not args.quiet:
        logger.setLevel(logging.INFO)
    if args.debug:
        logger.setLevel(logging.DEBUG)

    input_file = args.input

    if not Extractor.keepLinks:
        ignore_tag('a')

    if args.article:
        if args.templates:
            if os.path.exists(args.templates):
                with open(args.templates) as f:
                    load_templates(f)

        with open(input_file) as f:
            page = f.read().decode('utf-8')
            m = re.search(r'<id>(.*)</id>', page)
            page_id = m.group(1) if m else 0
            m = re.search(r'<title>(.*)</title>', page)
            title = m.group(1) if m else ''
            Extractor(page_id, title, [page]).extract()
        return

    output_dir = args.output
    if not os.path.isdir(output_dir):
        # noinspection PyBroadException
        try:
            os.makedirs(output_dir)
        except:
            logging.error('Could not create: %s', output_dir)
            return

    process_dump(input_file, args.templates, output_dir, file_size,
                 args.compress, args.threads)
