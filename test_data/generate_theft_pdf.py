from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

output_path = "D:/lbc/SuperDeepAnalyze/test_data/cases/004_wang_qiang_theft_case.pdf"

doc = SimpleDocTemplate(output_path, pagesize=A4,
                       rightMargin=2*cm, leftMargin=2*cm,
                       topMargin=2*cm, bottomMargin=2*cm)

story = []

# Try to register a Chinese font, fallback to default
font_dirs = [
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    "C:/Windows/Fonts/msyh.ttc",
]
font_registered = False
for fd in font_dirs:
    if os.path.exists(fd):
        try:
            pdfmetrics.registerFont(TTFont('Chinese', fd))
            font_registered = True
            break
        except:
            pass

title_style = ParagraphStyle('Title', fontSize=16, spaceAfter=12, alignment=1)
heading_style = ParagraphStyle('Heading', fontSize=13, spaceBefore=12, spaceAfter=6, fontName=font_registered and 'Chinese' or 'Helvetica-Bold')
normal_style = ParagraphStyle('Normal', fontSize=10, spaceAfter=4, fontName=font_registered and 'Chinese' or 'Helvetica')

content_parts = []

def add(text, style=normal_style):
    story.append(Paragraph(text, style))

add("王强等三人涉嫌盗窃罪案卷宗", title_style)
add("")
add("=" * 60)
add("")

add("案件基本信息", heading_style)
add("案件编号：BJ-2024-刑初字第0156号")
add("案件类型：刑事 - 盗窃罪")
add("管辖法院：北京市朝阳区人民法院")
add("公诉机关：北京市朝阳区人民检察院")
add("立案日期：2024年5月10日")
add("逮捕日期：2024年6月15日")
add("起诉日期：2024年8月20日")
add("开庭日期：2024年10月12日")
add("主审法官：张华")
add("公诉人：李伟")
add("")

add("一、案件概述", heading_style)
add("2024年1月至4月期间，被告人王强（男，1990年2月14日出生，"
    "汉族，河北省保定市人）、被告人李明（男，1987年9月3日出生，"
    "汉族，山东省济南市人）、被告人赵红（女，1992年12月20日出生，"
    "汉族，河南省郑州市人），以非法占有为目的，多次在北京市朝阳区、"
    "海淀区等地实施盗窃，盗窃对象包括高档小区、商场、办公楼等场所，"
    "盗窃财物包括现金、金银首饰、电子产品、名贵手表等，"
    "盗窃总价值共计人民币约185.6万元。")
add("")

add("二、涉案人员", heading_style)
add("王强（主犯）：犯罪集团发起者和组织者。曾于2018年因盗窃罪被判处有期徒刑两年，"
    "2020年刑满释放。在本次犯罪中负责踩点、制定盗窃计划、联系销赃渠道。")
add("李明（主犯）：负责具体实施盗窃。具有开锁技能，曾在锁具公司工作三年。"
    "负责技术性开锁和入室盗窃。")
add("赵红（从犯）：负责望风和销赃。利用其在二手奢侈品店工作的便利，"
    "联系销赃渠道。同时负责在盗窃现场附近望风，发现可疑情况及时通知同伙。")
add("")

add("三、犯罪事实", heading_style)
add("2024年1月8日，王强在朝阳区某高档小区踩点，发现3栋别墅业主长期外出。"
    "1月12日凌晨2时，王强、李明、赵红三人作案，通过李明技术开锁进入别墅，"
    "盗走现金35万元、名表（百达翡丽）一块价值约80万元、"
    "黄金首饰若干价值约12万元，合计约127万元。")
add("")
add("2024年2月3日，三人在海淀区某商场实施盗窃。"
    "利用夜间商场闭店后，通过消防通道进入商场一楼珠宝专柜，"
    "盗走黄金、钻石首饰共计价值约28万元。")
add("")
add("2024年2月20日，三人在朝阳区某写字楼15层某公司办公室实施盗窃，"
    "盗走公司保险柜内现金15万元、笔记本电脑3台价值约3万元，"
    "合计18万元。")
add("")
add("2024年3月15日，三人在海淀区另一高档小区实施盗窃，"
    "盗走现金8万元、苹果笔记本电脑2台价值约3.5万元、"
    "名牌包3个价值约4.5万元，合计16万元。")
add("")
add("2024年4月2日，三人在朝阳区某小区再次作案时，"
    "被小区保安发现并报警，当场抓获。"
    "现场查获作案工具（技术开锁工具一套、手套、头套等）以及"
    "部分被盗物品（笔记本电脑1台、名牌包1个）。")
add("")

add("四、证据清单", heading_style)
add("1. 现场监控录像（五处案发现场均提取）")
add("2. 指纹、DNA鉴定报告（从作案工具上提取到三被告人指纹）")
add("3. 被盗物品清单及估价报告（总价值约185.6万元）")
add("4. 销赃渠道证人证言（赵红联系的二手奢侈品店老板证言）")
add("5. 被告人供述与辩解")
add("6. 现场勘查笔录")
add("7. 抓获经过说明")
add("")

add("五、法律适用", heading_style)
add("三被告人的行为构成《中华人民共和国刑法》第二百六十四条规定的盗窃罪。")
add("盗窃数额特别巨大（185.6万元远超10万元标准），应在"
    "\"十年以上有期徒刑或者无期徒刑\"幅度内量刑。")
add("王强系累犯，依法应当从重处罚。")
add("赵红系从犯，依法应当从轻或减轻处罚。")
add("三人到案后部分供述犯罪事实，可酌情从轻处罚。")
add("")
add("涉案财物已部分追回（约45万元），其余赃物通过销赃渠道流失。")

doc.build(story)
print(f"PDF created: {output_path}")
