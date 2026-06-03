// Build the Mini-OGAS technical report as .docx
const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, ShadingType,
  WidthType, PageNumber, PageBreak, LevelFormat
} = require('docx');

const md = fs.readFileSync('docs/Mini-OGAS_技术报告_2026-05-30.md', 'utf-8');
const lines = md.split('\n');

// Constants
const BODY_FONT = 'SimSun';
const HEADING_FONT = 'Microsoft YaHei';
const MONO_FONT = 'Consolas';
const BODY_SIZE = 22; // 11pt in half-points
const CODE_SIZE = 17;  // 8.5pt

// A4: 11906 x 16838 DXA, 2.5cm margins = ~1417 DXA
const PAGE_WIDTH = 11906;
const PAGE_HEIGHT = 16838;
const MARGIN = 1417; // 2.5cm
const CONTENT_WIDTH = PAGE_WIDTH - MARGIN * 2; // ~9072

const children = [];
let i = 0;
let inCodeBlock = false;
let codeLines = [];
let codeLang = '';
let inTable = false;
let tableRows = [];

// -- Title Page --
children.push(
  new Paragraph({ spacing: { before: 4000 }, children: [] }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 600 },
    children: [new TextRun({ text: 'Mini-OGAS', font: HEADING_FONT, size: 72, bold: true, color: '1f2933' })]
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 200 },
    children: [new TextRun({ text: '分布式工厂制造执行系统', font: HEADING_FONT, size: 52, bold: true, color: '1f2933' })]
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 1200 },
    children: [new TextRun({ text: '技术报告', font: HEADING_FONT, size: 40, color: '4a5568' })]
  }),
  // Horizontal rule
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 200, after: 800 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: 'bcc8d4', space: 8 } },
    children: []
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
    children: [new TextRun({ text: '版本: v0.3.0', font: BODY_FONT, size: 24, color: '4a5568' })]
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
    children: [new TextRun({ text: '日期: 2026-05-30', font: BODY_FONT, size: 24, color: '4a5568' })]
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
    children: [new TextRun({ text: '环境: 开发/演示', font: BODY_FONT, size: 24, color: '4a5568' })]
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 120 },
    children: [new TextRun({ text: '项目性质: 研究生面试作品 / 分布式 MES 概念验证系统', font: BODY_FONT, size: 24, color: '4a5568' })]
  }),
  new Paragraph({ children: [new PageBreak()] })
);

// -- Helper functions --
function makeHeading(text, level) {
  const sizes = { 1: 36, 2: 30, 3: 26 };
  const headingLevels = { 1: HeadingLevel.HEADING_1, 2: HeadingLevel.HEADING_2, 3: HeadingLevel.HEADING_3 };
  return new Paragraph({
    heading: headingLevels[level],
    spacing: { before: level === 1 ? 400 : level === 2 ? 300 : 200, after: 160 },
    children: [new TextRun({ text, font: HEADING_FONT, size: sizes[level], bold: true, color: '1f2933' })]
  });
}

function makePara(text, opts = {}) {
  const runs = parseInlineFormatting(text, opts);
  return new Paragraph({
    spacing: { after: 120 },
    ...opts.paraOpts,
    children: runs
  });
}

function makeMonoBlock(text) {
  const textLines = text.split('\n');
  const runs = [];
  textLines.forEach((l, idx) => {
    if (idx > 0) runs.push(new TextRun({ break: 1 }));
    runs.push(new TextRun({ text: l, font: MONO_FONT, size: CODE_SIZE }));
  });
  return new Paragraph({
    spacing: { before: 80, after: 80 },
    indent: { left: 360 },
    shading: { fill: 'f4f6f8', type: ShadingType.CLEAR },
    children: runs
  });
}

function parseInlineFormatting(text, opts = {}) {
  // Handle inline code
  const parts = [];
  let remaining = text;
  let mono = opts.mono || false;

  // Bold **text**
  remaining = remaining.replace(/\*\*([^*]+)\*\*/g, (_, m) => `\x01B\x01${m}\x01b\x01`);
  // Inline code `text`
  remaining = remaining.replace(/`([^`]+)`/g, (_, m) => `\x01M\x01${m}\x01m\x01`);
  // Links [text](url)
  remaining = remaining.replace(/\[([^\]]+)\]\([^)]+\)/g, (_, m) => m);
  // HTML tags
  remaining = remaining.replace(/<[^>]+>/g, '');
  // Lt/gt entities
  remaining = remaining.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

  const fontName = opts.font || BODY_FONT;
  const fontSize = opts.size || BODY_SIZE;
  const fontColor = opts.color || '1f2933';

  // Parse markers
  const runs = [];
  let currentText = '';
  let inBold = false;
  let inMono = false;

  for (let j = 0; j < remaining.length; j++) {
    if (remaining[j] === '\x01') {
      if (currentText) {
        runs.push(new TextRun({
          text: currentText,
          font: inMono ? MONO_FONT : fontName,
          size: inMono ? CODE_SIZE : fontSize,
          bold: inBold,
          color: fontColor
        }));
        currentText = '';
      }
      const marker = remaining.substr(j + 1, 1);
      if (marker === 'B') inBold = true;
      else if (marker === 'b') inBold = false;
      else if (marker === 'M') inMono = true;
      else if (marker === 'm') inMono = false;
      j += 2;
    } else {
      currentText += remaining[j];
    }
  }
  if (currentText) {
    runs.push(new TextRun({
      text: currentText,
      font: inMono ? MONO_FONT : fontName,
      size: inMono ? CODE_SIZE : fontSize,
      bold: inBold,
      color: fontColor
    }));
  }
  return runs.length ? runs : [new TextRun({ text: '', font: fontName, size: fontSize })];
}

function makeBullet(text) {
  return new Paragraph({
    numbering: { reference: 'bullets', level: 0 },
    spacing: { after: 80 },
    children: parseInlineFormatting(text)
  });
}

function makeNumbered(text) {
  return new Paragraph({
    numbering: { reference: 'numbers', level: 0 },
    spacing: { after: 80 },
    children: parseInlineFormatting(text)
  });
}

// Process markdown
while (i < lines.length) {
  const line = lines[i];

  // Code blocks
  if (line.startsWith('```')) {
    if (inCodeBlock) {
      children.push(makeMonoBlock(codeLines.join('\n')));
      codeLines = [];
      inCodeBlock = false;
    } else {
      inCodeBlock = true;
      codeLang = line.slice(3).trim();
    }
    i++;
    continue;
  }

  if (inCodeBlock) {
    codeLines.push(line);
    i++;
    continue;
  }

  // Tables
  if (line.startsWith('|') && line.trim().endsWith('|')) {
    if (!inTable) { inTable = true; tableRows = []; }
    if (!/^\|[\s\-:|]+\|$/.test(line.trim())) {
      const cells = line.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
      tableRows.push(cells);
    }
    i++;
    continue;
  } else if (inTable) {
    if (tableRows.length > 0) {
      const colCount = Math.max(...tableRows.map(r => r.length));
      const colWidth = Math.floor(CONTENT_WIDTH / colCount);
      const headerBorder = { style: BorderStyle.SINGLE, size: 1, color: '1f2933' };
      const cellBorder = { style: BorderStyle.SINGLE, size: 1, color: 'd4dee7' };
      const cellBorders = { top: cellBorder, bottom: cellBorder, left: cellBorder, right: cellBorder };

      const rows = tableRows.map((row, ri) => {
        const isHeader = ri === 0;
        return new TableRow({
          children: row.map(cellText => new TableCell({
            borders: isHeader
              ? { top: headerBorder, bottom: headerBorder, left: headerBorder, right: headerBorder }
              : cellBorders,
            width: { size: colWidth, type: WidthType.DXA },
            shading: isHeader ? { fill: 'eef2f5', type: ShadingType.CLEAR } : undefined,
            margins: { top: 40, bottom: 40, left: 80, right: 80 },
            children: [new Paragraph({
              spacing: { after: 0 },
              children: [new TextRun({
                text: cellText || '',
                font: isHeader ? HEADING_FONT : BODY_FONT,
                size: 18,
                bold: isHeader,
                color: '1f2933'
              })]
            })]
          }))
        });
      });

      children.push(new Table({
        width: { size: CONTENT_WIDTH, type: WidthType.DXA },
        columnWidths: Array(colCount).fill(colWidth),
        rows
      }));
      children.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
    }
    inTable = false;
    tableRows = [];
    continue;
  }

  // Headings
  if (line.startsWith('### ')) {
    children.push(makeHeading(line.slice(4).trim(), 3));
  } else if (line.startsWith('## ')) {
    children.push(makeHeading(line.slice(3).trim(), 2));
  } else if (line.startsWith('# ')) {
    children.push(makeHeading(line.slice(2).trim(), 1));
  }
  // Horizontal rule
  else if (line.trim() === '---') {
    children.push(new Paragraph({
      spacing: { before: 200, after: 200 },
      border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: 'd4dee7', space: 4 } },
      children: []
    }));
  }
  // Blockquote
  else if (line.startsWith('> ')) {
    children.push(new Paragraph({
      indent: { left: 480 },
      spacing: { after: 80 },
      children: [new TextRun({ text: line.slice(2).trim(), font: BODY_FONT, size: BODY_SIZE, italics: true, color: '4a5568' })]
    }));
  }
  // Bullet list
  else if (/^  - /.test(line) || /^- /.test(line)) {
    children.push(makeBullet(line.replace(/^\s*-\s*/, '').trim()));
  }
  // Numbered list
  else if (/^\d+\.\s/.test(line)) {
    children.push(makeNumbered(line.replace(/^\d+\.\s*/, '').trim()));
  }
  // Empty line
  else if (line.trim() === '') {
    // skip
  }
  // Regular paragraph
  else {
    const text = line.trim();
    if (text && !text.startsWith('![') && !text.startsWith('<!--')) {
      children.push(makePara(text));
    }
  }
  i++;
}

// Flush any remaining table
if (inTable && tableRows.length > 0) {
  const colCount = Math.max(...tableRows.map(r => r.length));
  const colWidth = Math.floor(CONTENT_WIDTH / colCount);
  children.push(new Table({
    width: { size: CONTENT_WIDTH, type: WidthType.DXA },
    columnWidths: Array(colCount).fill(colWidth),
    rows: tableRows.map(row => new TableRow({
      children: row.map(cellText => new TableCell({
        width: { size: colWidth, type: WidthType.DXA },
        margins: { top: 40, bottom: 40, left: 80, right: 80 },
        children: [new Paragraph({ children: [new TextRun({ text: cellText || '', font: BODY_FONT, size: 18 })] })]
      }))
    }))
  }));
}

// Build document
const doc = new Document({
  numbering: {
    config: [
      {
        reference: 'bullets',
        levels: [{
          level: 0, format: LevelFormat.BULLET, text: '\u2022',
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } }
        }]
      },
      {
        reference: 'numbers',
        levels: [{
          level: 0, format: LevelFormat.DECIMAL, text: '%1.',
          alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } }
        }]
      }
    ]
  },
  styles: {
    default: {
      document: {
        run: { font: BODY_FONT, size: BODY_SIZE }
      }
    },
    paragraphStyles: [
      {
        id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: HEADING_FONT, size: 36, bold: true, color: '1f2933' },
        paragraph: { spacing: { before: 400, after: 200 }, outlineLevel: 0 }
      },
      {
        id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: HEADING_FONT, size: 30, bold: true, color: '1f2933' },
        paragraph: { spacing: { before: 300, after: 160 }, outlineLevel: 1 }
      },
      {
        id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: HEADING_FONT, size: 26, bold: true, color: '1f2933' },
        paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 2 }
      }
    ]
  },
  sections: [{
    properties: {
      page: {
        size: { width: PAGE_WIDTH, height: PAGE_HEIGHT },
        margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN }
      }
    },
    headers: {
      default: new Header({
        children: [new Paragraph({
          alignment: AlignmentType.RIGHT,
          children: [new TextRun({ text: 'Mini-OGAS 技术报告 v0.3.0', font: BODY_FONT, size: 18, color: '8899aa' })]
        })]
      })
    },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: 'Page ', font: BODY_FONT, size: 18, color: '8899aa' }),
            new TextRun({ children: [PageNumber.CURRENT], font: BODY_FONT, size: 18, color: '8899aa' })
          ]
        })]
      })
    },
    children
  }]
});

// Write output
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('docs/Mini-OGAS_技术报告_2026-05-30.docx', buf);
  console.log('Saved: docs/Mini-OGAS_技术报告_2026-05-30.docx');
  console.log(`Size: ${(buf.length / 1024).toFixed(1)} KB`);
});
