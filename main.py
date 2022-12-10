import os
import re
import urllib
import requests
from bs4 import BeautifulSoup, Tag
import json
from time import sleep
import base64
import xml.etree.ElementTree as ET
import shutil
from zipfile import ZipFile


sess = requests.Session()


def fetch_url(url, sleep_time=1):
    response = sess.get(url, headers=headers)
    sleep(sleep_time)
    return response


def filepath_from_url(url):
    return os.path.join(urllib.parse.urlparse(url).path.lstrip('/'))


def os_join(filepath):
    return os.path.join(output_filedir, filepath)


def download_url(url, sleep_time=1):
    filepath = filepath_from_url(url)
    if not os.path.exists(os_join(filepath)):
        response = sess.get(url, headers=headers)
        r_content = response.content
        sleep(sleep_time)
        if not os.path.exists(os.path.split(os_join(filepath))[0]):
            os.makedirs(os.path.split(os_join(filepath))[0])
        with open(os_join(filepath), 'wb') as f:
            f.write(r_content)
    return filepath


def toc_chapter_to_str(chapter, chapter_idx=1):
    chapter_path = chapter['path']
    chapter_name = chapter['title']
    c_str= f'''
    <navPoint id="navPoint-{chapter_idx}" playOrder="{chapter_idx}" class="chapter">
      <navLabel>
        <text>{chapter_name}</text>
      </navLabel>
      <content src="{chapter_path}" />'''
    if "contents" in chapter:
        for chapter_child in chapter["contents"]:
            chapter_child_str, chapter_idx = toc_chapter_to_str(chapter_child, chapter_idx)
            c_str += chapter_child_str
    # {"".join([toc_chapter_to_str(x) for x in (chapter["contents"] if "contents" in chapter else [])])}
    c_str += '''
    </navPoint>'''
    return c_str, chapter_idx+1


def make_toc(title, creator, toc_list):
    toc = f'''<?xml version='1.0' encoding='UTF-8' standalone='no' ?>
                <ncx version="2005-1" xmlns="http://www.daisy.org/z3986/2005/ncx/">
                  <head>
                    <meta name="dtb:depth" content="1" />
                    <meta name="dtb:totalPageCount" content="0" />
                    <meta name="dtb:maxPageNumber" content="0" />
                  </head>
                  <docTitle>
                    <text>{title}</text>
                  </docTitle>
                  <docAuthor>
                    <text>{creator}</text>
                  </docAuthor>
                  <navMap>'''
    i=1
    for chapter in toc_list:
        chapter, i = toc_chapter_to_str(chapter, i)
        toc += chapter
    toc += '  </navMap>\n</ncx>'
    return toc


def merge_url_paths(base_url, current_filepath, relative_url):
    return urllib.parse.urljoin(urllib.parse.urljoin(base_url, current_filepath), relative_url)


def download_epub(read_url, headers):
    base_url = read_url
    r = sess.get(read_url, headers=headers)

    bData = json.loads(re.search('window.bData = (.+)', str(r.text)).group(1).strip('; '))
    xhtml_urls = [urllib.parse.urljoin(read_url, x['path']) for x in bData['spine']]
    match_xhtml_base64 = "(?<=self,')[^']*(?=')"

    title = bData['title']['main']
    global output_filedir
    creator = bData['creator'][0]['name']
    output_filedir = f'{title[:30]} - {creator[:30]}'

    xhtml_filepaths = []
    for url in xhtml_urls:
        filepath = filepath_from_url(url)
        if not os.path.exists(os_join(filepath)):
            html = fetch_url(url).text
            soup = BeautifulSoup(html, features="lxml")
            # see if it needs styling
            style_elems = soup.find_all('link', rel="stylesheet")
            for style_elem in style_elems:
                style_elem['href'] = \
                download_url(urllib.parse.urljoin(base_url, style_elem['href']))
            html = base64.b64decode(re.search(match_xhtml_base64, html).group())
            body_soup = BeautifulSoup(html, "html.parser")
            # body_soup = Tag(soup, html.decode('utf-8'))
            soup.find('body').replaceWith(body_soup)

            # for style_elem in style_elems:
            #     body_soup.html.insert(0, style_elem)
            print(filepath, html)
            if os.path.split(filepath)[0]:
                if not os.path.exists(os_join(os.path.split(filepath)[0])):
                    os.makedirs(os_join(os.path.split(filepath)[0]), exist_ok=True)
            with open(os_join(filepath), 'w', encoding='utf-8') as f:
                f.write(str(soup))
        xhtml_filepaths.append(filepath)

    filepaths = []
    # download all imgs in html files
    for xhtml_filepath in xhtml_filepaths:
        html = open(os_join(xhtml_filepath), 'r', errors='ignore').read()
        soup = BeautifulSoup(html, features="lxml")

        # # download all stylesheets or whatever else has href
        # for elem in soup.find_all(href=True):
        #     print(download_url(elem['href']))
        filepaths += [download_url(merge_url_paths(base_url, xhtml_filepath, x['href']))
                      for x in soup.find_all('link', rel="stylesheet")]
        for html_img in soup.find_all('image'):
            url = merge_url_paths(base_url, xhtml_filepath, html_img['xlink:href'])
            filepaths.append(download_url(url))

        for html_img in soup.find_all('img'):
            url = merge_url_paths(base_url, xhtml_filepath, html_img['src'])
            print(html_img['src'], url)
            try:filepaths.append(download_url(url))
            except:
                print('error downloading', url)

    for css_file in {x for x in filepaths if x.endswith('.css')}:
        with open(os_join(css_file), 'r') as f:
            file_txt = f.read()
            for url in re.findall('(?<=url\\()[^")]+', file_txt):
                print(url)
                download_url(merge_url_paths(base_url, css_file, url.strip('"')))

    # get the required title.opf and META-INF/container.xml file that points to it
    root = ET.Element("package")
    root.attrib = {"xmlns": "http://www.idpf.org/2007/opf", "unique-identifier": "bookid", "version": "2.0"}
    m1 = ET.Element("metadata")
    root.append(m1)
    m1.attrib = {"xmlns:dc": "http://purl.org/dc/elements/1.1/"}

    m2 = ET.Element("dc:title")
    m2.text = title
    m1.append(m2)

    m3 = ET.Element("dc:creator")
    m3.text = bData['creator'][0]['name']
    m1.append(m3)

    m4 = ET.Element("dc:language")
    m4.text = bData['language']
    m1.append(m4)

    m5 = ET.Element("dc:description")
    m5.text = bData['description']['full']
    m1.append(m5)


    manifest = ET.Element("manifest")
    #    <opf:item href="toc.ncx" id="ncx" media-type="application/x-dtbncx+xml"/>
    mani_item = ET.Element("item")
    mani_item.attrib = {'href': 'toc.ncx', "id": "ncx", "media-type": "application/x-dtbncx+xml"}
    manifest.append(mani_item)

    spine = ET.Element("spine")
    # spine.attrib = {"toc": "ncx"}  # probably dont need this
    for xhtml_filepath in xhtml_filepaths:
        xhtml_filename = os.path.split(xhtml_filepath)[-1]
        mani_item = ET.Element("item")
        manifest_item_attrs = {"href": xhtml_filepath, "id": xhtml_filename, "media-type": "application/xhtml+xml"}
        mani_item.attrib = manifest_item_attrs
        manifest.append(mani_item)

        spine_item = ET.Element("itemref")
        spine_item.attrib = {"idref": xhtml_filename}
        spine.append(spine_item)


    root.append(manifest)
    root.append(spine)

    opf_filename = f"{title[:40]}.opf"

    tree = ET.ElementTree(root)
    ET.indent(tree, space=' ')
    opf_filepath = os_join(opf_filename)
    tree.write(opf_filepath)

    container_xml = f'''<?xml version="1.0"?>
    <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
      <rootfiles>
        <rootfile full-path="{opf_filename}" media-type="application/oebps-package+xml"/>
      </rootfiles>
    </container>
    '''


    with open(os_join('toc.ncx'), 'w', encoding='utf-8') as f:
        f.write(make_toc(title, creator, bData['nav']['toc']))

    container_xml_filepath = os_join(os.path.join('META-INF', 'container.xml'))
    os.makedirs(os.path.split(container_xml_filepath)[0], exist_ok=True)
    with open(container_xml_filepath, 'w', encoding='utf-8') as f:
        f.write(container_xml)

    if os.path.exists(f'{output_filedir}.epub'):
        os.remove(f'{output_filedir}.epub')

    with ZipFile(f'{output_filedir}.epub', 'w') as zip_f:
        zip_f.writestr("mimetype", 'application/epub+zip')
        for path, directories, files in os.walk(output_filedir):
            for filename in files:
                filepath = os.path.join(path, filename)
                zip_f.write(filepath, arcname=os.path.join(*filepath.split(os.sep)[1:])) # zipping the file

    shutil.rmtree(output_filedir)
    return True


if __name__ == '__main__':
    url = 'https://blah.read.overdrive.com/?d='
    headers = {'Cookie': ''}
    download_epub(url, headers=headers)
