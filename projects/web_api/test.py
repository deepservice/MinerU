import requests
 
headers = {
    'accept': 'application/json',
}
 
params = {
    'parse_method': 'auto',
    'is_json_md_dump': 'false',
    'output_dir': 'output',
    'return_layout': 'false',
    'return_info': 'false',
    'return_content_list': 'false',
    'return_images': 'false',
}
files = {
    'pdf_file': ('测试.pdf', open('测试.pdf', 'rb'), 'application/pdf'),
}
print(files)
response = requests.post('http://localhost:10086/pdf_parse', params=params, headers=headers, files=files)
print(response.json())