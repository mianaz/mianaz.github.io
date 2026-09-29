"""Build the standalone offline HTML from the local source files."""
from pathlib import Path
root=Path(__file__).resolve().parent
text=(root/'template.html').read_text(encoding='utf-8')
for token,name in [('DATA','data.json'),('ALLOCATOR','allocator.js'),('PLANNER','planner.js'),('APP','app.js')]:
    content=(root/name).read_text(encoding='utf-8')
    # Prevent strings inside imported data/source from closing an inline script.
    content=content.replace('</script','<\\/script')
    text=text.replace('__'+token+'__',content)
(root/'index.html').write_text(text,encoding='utf-8')
print('Built',root/'index.html')
