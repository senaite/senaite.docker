import urllib2, base64, re

def fetch(url):
    req = urllib2.Request(url)
    req.add_header('Authorization', 'Basic ' + base64.b64encode('admin:admin'))
    return urllib2.urlopen(req).read()

# Find worksheet IDs
html = fetch('http://localhost:8080/Senaite10/worksheets')
links = re.findall(r'href="[^"]*worksheets/([^"/]+)"', html)
for l in sorted(set(links)):
    if l:
        print('Worksheet:', l)

# Fetch the first worksheet's manage_results page
if links:
    ws_id = sorted(set(links))[0]
    url = 'http://localhost:8080/Senaite10/worksheets/%s/manage_results' % ws_id
    print('\nFetching:', url)
    html = fetch(url)
    with open('/tmp/manage_results_classic.html', 'w') as f:
        f.write(html)
    print('Saved, length:', len(html))
    
    # Look for workflow-related HTML
    for pattern in ['contentviews', 'workflow', 'transition', 'submit', 'save', 'id="workflow', 'class="portalMessage', 'state-title']:
        idx = html.lower().find(pattern.lower())
        if idx >= 0:
            print('\nFound "%s" at position %d:' % (pattern, idx))
            print(html[max(0,idx-100):idx+200])
            print('---')
