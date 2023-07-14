from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor
from termcolor import colored
from rfc3987 import parse
from tqdm import tqdm
import itertools
import requests
import urllib3
import sys
import re


def print_banner():
    print('''\nCloudScraper is a tool to search through the source code of websites in order to find cloud resources belonging to a target.
    by Jordan Potti
    @ok_bye_now\n'''
    )


def checker(url):
    '''
    Check if the url is a valid one or not.
    '''
    try:
        parse(url)
        return True
    except ValueError:
        return False
    return False


def gather_links(html):
    '''
    Apply to the raw HTML a regular expression to gather all the urls.
    '''
    urls = []
    links_ = re.findall('http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\), ]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', html)
    urls.extend(filter(checker, links_)) #filter the ones that don't compile with the checker function

    del(links_)
    return list(set(urls))


def start(target):
    '''
        Load the initial url and gather the first urls that will be used
        by the spider to keep looking for more links
    '''
    print(colored("Beginning search for cloud resources in {}".format(target), color='cyan'))

    try:
        html = requests.get(target, allow_redirects=True, headers=headers, verify=arguments.no_verify).text
        links = gather_links(html)

    except requests.exceptions.RequestException as e:
        if arguments.v:
            print(colored('Network error: {}'.format(e), 'red', attrs=['bold']))
        return

    print(colored('Initial links: {}\n'.format(len(links)), color='cyan'))
    spider(links, target)


def worker(url):
    '''
        Function handling all the crawling action of the spider.
        It first checks the desired depth and if the domain of
        the url matches the target to avoid crawling other web sites.
        Makes a GET request, parses the HTML and returns all the links.
    '''
    if url.count("/") <= arguments.depth+2:
        try:
            html = requests.get(url, allow_redirects=True, headers=headers, verify=arguments.no_verify).text
            links = gather_links(html)

        except requests.exceptions.RequestException as e:
            if arguments.v:
                print(colored('Network error: {}'.format(e), 'red', attrs=['bold']))
            return []

        print('{} links found [{}]'.format(len(links), url))
        return links

    else:
        return []


def spider(base_urls, target):
    '''
        Loop through the initial links found in the given page. Each new link
        discovered will be added to the list if it's not already there, and thus
        crawled aswell looking for more links.

        wannabe list works as the placeholder for the urls that are yet to crawl.
        base_urls is a list with all the already crawled urls.
    '''
    global target_
    target_ = parse(target)

    with ThreadPoolExecutor(max_workers=arguments.process) as executor:
        wannabe = [url for url in base_urls if target_['authority'] in parse(url)['authority']]

        while True:
            # Add progress bar with tqdm
            pbar = tqdm(total=len(wannabe), desc='Processing URLs', ncols=80)
            #retrieve all the urls returned by the workers
            new_urls = list(executor.map(worker, wannabe))
            # Update the progress bar
            pbar.update(len(new_urls))
            #flatten them and remove repeated ones
            new_urls = list(set(itertools.chain(*new_urls)))
            wannabe = []
            i = 0

            #if new_urls is empty meaning no more urls are being discovered, exit the loop
            if not new_urls:
                break
            
            else:
                for url in new_urls:
                    if url not in base_urls:
                        '''
                        For each new url, check if it hasn't been crawled. If it's 
                        indeed new and contains the target domain it gets appended to 
                        the wannabe list so in the next iteration it will be crawled. 
                        '''
                        i += 1
                        if target_['authority'] in parse(url)['authority']:
                            wannabe.append(url)
                        base_urls.append(url)
            
            print(colored('\nNew urls appended: {}\n'.format(i), 'green', attrs=['bold']))
            pbar.close()

        #once all the links for the given depth have been analyzed, execute the parser
        parser(base_urls)


def parser(links):
    '''
        Once all the links have been gathered check how many of them
        match with the list of cloud domains we are interested in.
    '''
    print(colored('Parsing results...', 'cyan', attrs=['bold']))
    matches = []

    [[matches.append(link) for link in links if cloud_domain in link] for cloud_domain in cloud_domains]
    matches = list(set(matches))
    
    print('\nTotal links: ', len(links))
    if len(matches) == 0:
        print(colored("There were no matches!", 'red', attrs=['bold']))
    
    else:
        print(colored("There were {} matches for this search!".format(len(matches)), 'green', attrs=['bold']))
        [print(match, "\n") for match in matches]


def args():
    parser = ArgumentParser()
    parser.add_argument("-u", dest="URL", required=False, help="Target Scope") 
    parser.add_argument("-d", dest="depth", type=int, required=False, default=5, help="Max Depth of links Default: 5")
    parser.add_argument("-l", dest="targetlist", required=False, help="Location of text file of Line Delimited targets") 
    parser.add_argument("-v", action="store_true", default=False, required=False, help="Verbose output")
    parser.add_argument("-p", dest="process", required=False, default=2, type=int, help="Number of processes to run")
    parser.add_argument("-k", dest="keywords", required=False, default=[], nargs='+', help="Keywords to search for")
    parser.add_argument("--keywords-file", dest="keywords_file", required=False, help="File with keywords to search for, one per line")
    parser.add_argument("--no-verify", action="store_false", default=True, required=False, help="Skip TLS verification")
    if len(sys.argv) == 1:
        parser.error("No arguments given.")
        parser.print_usage
        sys.exit()

    #output parsed arguments into a usable object
    return parser.parse_args()


def cleaner(url):
    if 'http' not in url:
        return ("https://"+url).strip()
    else:
        return url.strip()


def main():
    global cloud_domains
    if arguments.keywords:
        cloud_domains = arguments.keywords
    if arguments.keywords_file:
        with open(arguments.keywords_file, 'r') as kf:
            cloud_domains = [line.strip() for line in kf.readlines()]
    if arguments.targetlist:
        with open (arguments.targetlist, 'r') as target_list:
            [start(cleaner(line)) for line in target_list]
    else:
        start(cleaner(arguments.URL))


headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36'
}
arguments = args()

# If we passed --no-verify then we likely don't care about insecure request warnings.
if arguments.no_verify:
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

cloud_domains = ['amazonaws.com', 'digitaloceanspaces.com', 'windows.net', 'storage.googleapis.com', 'aliyuncs.com']

if __name__ == '__main__':
    print_banner()
    main()
