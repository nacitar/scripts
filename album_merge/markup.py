#!/usr/bin/env python3

import xml.etree.ElementTree as ET
import io
from timestamp import Timestamp

def loadXML(filename):
    return ET.parse(filename).getroot()

class Node(object):
    def __init__(self, element):
        self.set_element(element)

    def element(self):
        return self._element

    def set_element(self, element):
        self._element = element

    def tag(self):
        return self.element().tag

    def set_tag(self, tag):
        self.element().tag = tag

    def add_comment(self, text):
        self.element().append(ET.Comment(text))

    # Creates the child if it is missing
    @staticmethod
    def child(parent, tag):
        children = parent.findall(tag)
        if not children:
            element = ET.SubElement(parent, tag)
        elif len(children) == 1:
            element = children[0]
        else:
            raise RuntimeError('Too many {} children: {}'.format(
                    tag, len(children)))
        return element

    def write(self, handle, encoding='utf-8', xml_declaration=False,
            doctype = None):
        encoding = encoding.lower()
        # if we want this in a string
        is_unicode = (encoding == 'unicode')
        header = ''
        if xml_declaration:
            # header says utf-8 if unicode
            header += '<?xml version="1.0" encoding="{}"?>\n'.format(
                    'utf-8' if is_unicode else encoding)
        if doctype is not None:
            header += '<!DOCTYPE {} SYSTEM "{}">\n'.format(
                    self.tag(), doctype)
        if header:
            # only encode if not using unicode
            if not is_unicode:
                header = header.encode(encoding)
            handle.write(header)

        ET.ElementTree(self.element()).write(handle, encoding=encoding,
                xml_declaration=False)

    def prettify(self, indent='  '):
        queue = [(0, self.element())]  # (level, element)
        while queue:
            level, element = queue.pop(0)
            children = [(level + 1, child) for child in list(element)]
            if children:
                element.text = '\n' + indent * (level+1)  # for child open
            if queue:
                element.tail = '\n' + indent * queue[0][0]  # for sibling open
            else:
                element.tail = '\n' + indent * (level-1)  # for parent close
            queue[0:0] = children  # prepend so children come before siblings

    def __str__(self):
        handle = io.StringIO()
        self.write(handle, encoding='unicode')
        return handle.getvalue()

    # sets the target to the provided value, and if the value is non-empty the
    # child is added to parent, otherwise the child is remove from parent.
    @staticmethod
    def set_target_and_child_state(parent, child, target, value, append=True):
        if value:
            target.text = value

            if child not in parent:
                if append:
                    parent.append(child)
                else:
                    parent.insert(0, child)
        else:
            target.text = ''
            try:
                parent.remove(child)
            except ValueError:
                pass # child not present


class Container(Node):
    def __init__(self, element, child_tag):
        super().__init__(element)
        self.set_child_tag(child_tag)

    def child_tag(self):
        return self._child_tag

    def set_child_tag(self, child_tag):
        self._child_tag = child_tag

    def clear(self):
        for child in self.children():
            self.element().remove(child)

    def children(self):
        if self.child_tag():
            children = self.element().findall(self.child_tag())
        else:
            children = list(self.element())
        return children

    def append(self, element):
        if self.child_tag() and self.child_tag() != element.tag():
            raise RuntimeError('This container is for another tag type.')
        self.element().append(element.element())

    def extend(self, elements):
        for element in elements:
            self.append(element)

    def remove(self, element):
        self.element().remove(element.element())


# TODO: chapters can contain subchapters!
# https://matroska.org/technical/specs/tagging/example-audio.html#whole
# https://matroska.org/technical/specs/chapters/index.html
# https://github.com/mbunkus/mkvtoolnix/blob/master/examples/matroskatags.dtd
# https://github.com/mbunkus/mkvtoolnix/blob/master/examples/matroskachapters.dtd
class Chapter(Node):
    ROOT = 'ChapterAtom'
    def __init__(self, uid=None, start_time=None, name=None, element=None):
        if element is None:
            element = ET.Element(Chapter.ROOT)
        super().__init__(element)

        self._start = Node.child(element, 'ChapterTimeStart')
        self._uid = Node.child(element, 'ChapterUID')
        self._hidden = Node.child(element, 'ChapterFlagHidden')
        self._enabled = Node.child(element, 'ChapterFlagEnabled')

        # NOT adding!
        self._display = Node.child(element, 'ChapterDisplay')

        self._name = Node.child(self._display, 'ChapterString')
        self._name_language = Node.child(self._display, 'ChapterLanguage')

        if not self._enabled.text:
            self.set_enabled(True)
        if not self._hidden.text:
            self.set_hidden(False)
        if not self.name_language():
            self.set_name_language('eng')
        if not self._start.text:
            self.set_start_time(0)
        if not self.name():
            self.set_name('')  # removes it

        self.set(uid=uid, start_time=start_time, name=name)

    def set(self, uid=None, start_time=None, name=None):
        if uid is not None:
            self.set_uid(uid)
        if start_time is not None:
            self.set_start_time(start_time)
        if name is not None:
            self.set_name(name)

    def uid(self):
        return int(self._uid.text)

    def set_uid(self, uid):
        self._uid.text = str(uid)

    def name(self):
        return self._name.text

    def set_name(self, name):
        Node.set_target_and_child_state(self.element(), self._display,
                self._name, name, True)

    def name_language(self):
        return self._name_language.text

    def set_name_language(self, name_language):
        self._name_language.text = name_language

    def start_time(self):
        return Timestamp(self._start.text)

    def set_start_time(self, start_time):
        if not isinstance(start_time, Timestamp):
            start_time = Timestamp(start_time)
        self._start.text = str(start_time)

    def enabled(self):
        return (self._enabled.text == '1')

    def set_enabled(self, enabled):
        self._enabled.text = '1' if enabled else '0'

    def hidden(self):
        return (self._hidden.text == '1')

    def set_hidden(self, hidden):
        self._hidden.text = '1' if hidden else '0'


class ChapterFile(Node):
    ROOT = 'Chapters'
    def __init__(self, element=None):
        if element is None:
            element = ET.Element(ChapterFile.ROOT)
        super().__init__(element)
        self._edition = Node.child(element, 'EditionEntry')
        self._uid = Node.child(self._edition, 'EditionUID')
        self._hidden = Node.child(self._edition,
                'EditionFlagHidden')
        self._default = Node.child(self._edition,
                'EditionFlagDefault')

        self._chapters = Container(self._edition, Chapter.ROOT)

        if not self.default():
            self.set_default(False)
        if not self.hidden():
            self.set_hidden(False)

    def chapters(self):
        return self._chapters;

    # changing the defaults, because this one is a file
    def write(self, handle, encoding='utf-8', xml_declaration=True,
            doctype='matroskachapters.dtd'):
        self.prettify()
        super().write(handle, encoding=encoding,
                xml_declaration=xml_declaration, doctype=doctype)

    def uid(self):
        return int(self._uid.text)

    def set_uid(self, uid):
        self._uid.text = str(uid)

    def default(self):
        return (self._default.text == '1')

    def set_default(self, default):
        self._default.text = '1' if default else '0'

    def hidden(self):
        return (self._hidden.text == '1')

    def set_hidden(self, hidden):
        self._hidden.text = '1' if hidden else '0'


class Field(Node):
    ROOT='Simple'
    def __init__(self, name=None, value=None, language=None,
            default_language=None, element=None):
        if element is None:
            element = ET.Element(Field.ROOT)
        super().__init__(element)
        self._name = Node.child(element, 'Name')
        self._value = Node.child(element, 'String')
        self._language = Node.child(element, 'TagLanguage')
        # set to 0 if it is translated from another language
        self._default_language = Node.child(element,
                'DefaultLanguage')

        if not self.language():
            self.set_language('eng')
        if not self.default_language():
            self.set_default_language('1')

        self.set(name=name, value=value, language=language,
                default_language=default_language)

    def set(self, name=None, value=None, language=None,
            default_language=None):
        if name is not None:
            self.set_name(name)
        if value is not None:
            self.set_value(value)
        if language is not None:
            self.set_language(language)
        if default_language is not None:
            self.set_default_language(default_language)

    def name(self):
        return self._name.text

    def set_name(self, name):
        self._name.text = name

    def value(self):
        return self._value.text

    def set_value(self, value):
        self._value.text = value

    def language(self):
        return self._language.text

    def set_language(self, language):
        self._language.text = language

    def default_language(self):
        return (self._default_language.text == '1')

    def set_default_language(self, is_default_language):
        self._default_language.text = '1' if is_default_language else '0'

class Tag(Node):
    ROOT='Tag'
    def __init__(self, target_type_value=None, target_type=None,
            chapter_uid=None, fields=None, element=None):
        if element is None:
            element = ET.Element(Tag.ROOT)
        super().__init__(element)
        self._target = Node.child(element, 'Targets')
        self._target_type = Node.child(self._target, 'TargetType')
        self._target_type_value = Node.child(self._target,
                'TargetTypeValue')
        self._chapter_uid = Node.child(self._target, 'ChapterUID')

        self._fields = Container(element, Field.ROOT)

        if not self.chapter_uid():
            self.set_chapter_uid('')  # will remove it

        self.set(target_type_value=target_type_value, target_type=target_type,
                chapter_uid=chapter_uid, fields=fields)

    def set(self, target_type_value=None, target_type=None,
            chapter_uid=None, fields=None):
        if target_type_value is not None:
            self.set_target_type_value(target_type_value)
        if target_type is not None:
            self.set_target_type(target_type)
        if chapter_uid is not None:
            self.set_chapter_uid(chapter_uid)
        if fields is not None:
            self.fields().clear()
            self.fields().extend(fields)

    def chapter_uid(self):
        value = self._chapter_uid.text
        if value is not None:
            return int(value)
        return 0

    def set_chapter_uid(self, uid):
        Node.set_target_and_child_state(
                self._target, self._chapter_uid, self._chapter_uid, str(uid), append=False)

    def target_type(self):
        return self._target_type.text

    def set_target_type(self, target_type):
        self._target_type.text = target_type

    def target_type_value(self):
        return self._target_type_value.text

    def set_target_type_value(self, target_type_value):
        self._target_type_value.text = target_type_value

    def fields(self):
        return self._fields


class TagFile(Node):
    ROOT = 'Tags'

    def __init__(self, tags=None, element=None):
        if element is None:
            element = ET.Element(TagFile.ROOT)
        super().__init__(element)
        self._tags = Container(self.element(), Tag.ROOT)
        self.set(tags=tags)

    def set(self, tags=None):
        if tags is not None:
            self.tags().clear()
            self.tags().extend(tags)

    def tags(self):
        return self._tags

    # changing the defaults, because this one is a file
    def write(self, handle, encoding='utf-8', xml_declaration=True,
            doctype='matroskatags.dtd'):
        self.prettify()
        super().write(handle, encoding=encoding,
                xml_declaration=xml_declaration, doctype=doctype)


class Picture(Node):
    ROOT = 'Picture'

    def __init__(self, name=None, filename=None, description=None, element=None):
        if element is None:
            element = ET.Element(Picture.ROOT)
        super().__init__(element)
        self._name = Node.child(element, 'Name')
        self._filename = Node.child(element, 'FileName')
        self._description = Node.child(element, 'Description')

        if name is not None:
            self.set_name(name)
        if filename is not None:
            self.set_filename(filename)
        if description is not None:
            self.set_description(description)

    def name(self):
        return self._name.text

    def set_name(self, value):
        self._name.text = value

    def filename(self):
        return self._filename.text

    def set_filename(self, value):
        self._filename.text = value

    def description(self):
        return self._description.text

    def set_description(self, value):
        self._description.text = value

class PictureFile(Node):
    ROOT = 'Pictures'
    def __init__(self, pictures=None, element=None):
        if element is None:
            element = ET.Element(PictureFile.ROOT)
        super().__init__(element)
        self._pictures = Container(element, Picture.ROOT)
        if pictures is not None:
            self.set(pictures=pictures)

    def set(self, pictures):
        if pictures is not None:
            self.pictures().clear()
            self.pictures().extend(pictures)

    def pictures(self):
        return self._pictures

    # changing the defaults, because this one is a file
    def write(self, handle, encoding='utf-8', xml_declaration=True,
            doctype=None):
        self.prettify()
        super().write(handle, encoding=encoding,
                xml_declaration=xml_declaration, doctype=doctype)

