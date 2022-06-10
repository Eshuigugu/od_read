import os
import re
import urllib
import requests
from bs4 import BeautifulSoup
import json
from time import sleep
import base64
import xml.etree.ElementTree as ET
import shutil


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
        html = fetch_url(url).text
        soup = BeautifulSoup(html, features="lxml")
        # see if it needs styling
        style_elems = soup.find_all('link', rel="stylesheet")
        for style_elem in style_elems:
            style_elem['href'] = download_url(urllib.parse.urljoin(base_url, style_elem['href']))
        html = base64.b64decode(re.search(match_xhtml_base64, html).group())
        soup = BeautifulSoup(html, features="lxml")
        for style_elem in style_elems:
            soup.html.insert(0, style_elem)
        filepath = filepath_from_url(url)
        print(html)
        if os.path.split(filepath)[0]:
            os.makedirs(os.path.split(filepath)[0], exist_ok=True)
        with open(os_join(filepath), 'w', encoding='utf-8') as f:
            f.write(soup.prettify())
        xhtml_filepaths.append(filepath)


    # download all imgs in html files
    for xhtml_filepath in xhtml_filepaths:
        html = open(os_join(xhtml_filepath), 'r', errors='ignore').read()
        soup = BeautifulSoup(html, features="lxml")

        # download all stylesheets or whatever else has href
        for elem in soup.find_all(href=True):
            print(download_url(elem['href']))

        for html_img in soup.find_all('image'):
            url = urllib.parse.urljoin(base_url, html_img['xlink:href'])
            print(download_url(url))

        for html_img in soup.find_all('img'):
            url = urllib.parse.urljoin(base_url, html_img['src'])
            print(download_url(url))

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
    container_xml_filepath = os_join(os.path.join('META-INF', 'container.xml'))
    os.makedirs(os.path.split(container_xml_filepath)[0], exist_ok=True)
    with open(container_xml_filepath, 'w', encoding='utf-8') as f:
        f.write(container_xml)

    if os.path.exists(f'{output_filedir}.epub'):
        os.remove(f'{output_filedir}.epub')
    os.rename(shutil.make_archive(output_filedir, 'zip', output_filedir), f'{output_filedir}.epub')
    shutil.rmtree(output_filedir)
    return True


if __name__ == '__main__':
    url = 'https://blah.read.overdrive.com/?d='
    headers = {
        'Cookie': '',
            'User-Agent': ''}
    download_epub(url, headers=headers)
