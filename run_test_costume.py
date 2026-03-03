import json

costumes_json = '[{"name": "Costume 1", "image_url": "url1", "shiny_image_url": "s_url1"}]'
available_costumes = json.loads(costumes_json)
print(available_costumes)
