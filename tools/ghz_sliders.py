# Lists the number sliders of a Grasshopper 2 .ghz file without Rhino: name, value and range as a Markdown table.
#   python ghz_sliders.py "examples/nist-ftc08/FTC-08 parametric.ghz"
# A .ghz is a zip; the sliders are read straight from the binary Document.root (decimal values), so this works
# on any machine with Python 3. Handy for diffing parameter sets or pasting a slider table into an AI chat.
import zipfile,re,struct,sys
z=zipfile.ZipFile(sys.argv[1]);d=z.read('Document.root')
def dec(seg,name):
    k=seg.find(bytes([len(name)])+name.encode()+b'\xff\xff\xff\xff\x00\x08\x00\x00')
    b=seg[k+1+len(name)+8:][:16]
    lo,mid,hi,fl=struct.unpack('<IIII',b)
    v=(hi<<64|mid<<32|lo)/10**((fl>>16)&0xff)
    return -v if fl>>31 else v
out=[]
for m in re.finditer(rb'parameter: "([^"]+)"\x04name\xff\xff\xff\xff\x00@\x00\x00.Grasshopper2\.Parameters\.Special\.NumberSliderObject',d):
    nm=m.group(1).decode('utf8','replace'); seg=d[m.end():m.end()+6000]
    l,u,v=[dec(seg,f) for f in ('Lower','Upper','Value')]
    g=lambda x: ('%g'%x)
    out.append("| %s | %s | %s..%s |"%(nm,g(v),g(l),g(u)))
print("| Slider | Value | Range |\n|---|---|---|")
print("\n".join(out)); print(len(out))
