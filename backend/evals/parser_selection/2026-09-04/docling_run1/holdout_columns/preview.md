With this data model, Docling enables representing document content in a unified manner, i.e., regardless of the source document format.

Besides specifying the data model, the DoclingDocument class defines APIs encompassing document construction, inspection, and export. Using the respective methods, users can incrementally build a DoclingDocument , traverse its contents in reading order, or export to commonly used formats. Docling supports lossless serialization to (and deserialization from) JSON, and lossy export formats such as Markdown and HTML, which, unlike JSON, cannot retain all available meta information.

A DoclingDocument can additionally be passed to a chunker class, an abstraction that returns a stream of chunks, each of which captures some part of the document as a string accompanied by respective metadata. To enable both flexibility for downstream applications and out-of-the-box utility, Docling defines a chunker class hierarchy, providing a base type as well as specific subclasses. By using the base chunker type, downstream applications can leverage popular frameworks like LangChain or LlamaIndex, which provide a high degree of flexibility in the chunking approach. Users can therefore plug in any built-in, self-defined, or third-party chunker implementation.

## 3.2 Parser Backends

Document formats can be broadly categorized into two types:

1. Low-level formats , like PDF files or scanned images. These formats primarily encode the visual representation of the document, containing instructions for rendering text cells and lines or defining image pixels. Most semantics of the represented content are typically lost and need to be recovered through specialized AI methods, such as OCR, layout analysis, or table structure recognition.
2. Markup-based formats , including MS Office, HTML, Markdown, and others. These formats preserve the semantics of the content (e.g., sections, lists, tables, and figures) and are comparatively inexpensive to parse.

Docling implements several parser backends to read and interpret different formats and it routes their output to a fitting processing pipeline. For PDFs Docling provides backends which: a) retrieve all text content and their geometric properties, b) render the visual representation of each page as it would appear in a PDF viewer. For markup-based formats, the respective backends carry the responsibility of creating a DoclingDocument representation directly. For some formats, such as PowerPoint slides, element locations and page provenance are available, whereas in other formats (for example, MS Word or HTML), this information is unknown unless rendered in a Word viewer or a browser. The DoclingDocument data model handles both cases.

PDF Backends While several open-source PDF parsing Python libraries are available, in practice we ran into various limitations, among which are restrictive licensing (e.g., pymupdf (pym 2024)), poor speed, or unrecoverable quality issues, such as merged text cells across far-apart text tokens or table columns (pypdfium, PyPDF) (PyPDFium Team 2024; pypdf Maintainers 2024).

We therefore developed a custom-built PDF parser, which is based on the low-level library qpdf (Berkenbilt 2024). Our PDF parser is made available in a separate package named docling-parse and acts as the default PDF backend in Docling. As an alternative, we provide a PDF backend relying on pypdfium (PyPDFium Team 2024).

Other Backends Markup-based formats like HTML, Markdown, or Microsoft Office (Word, PowerPoint, Excel) as well as plain formats like AsciiDoc can be transformed directly to a DoclingDocument representation with the help of several third-party format parsing libraries. For HTML documents we utilize BeautifulSoup (Richardson 2004-2024), for Markdown we use the Marko library (Ming 2019-2024), and for Office XML-based formats (Word, PowerPoint, Excel) we implement custom extensions on top of the python-docx (Canny and contributors 2013-2024a), python-pptx (Canny and contributors 20132024b), and openpyxl (Eric Gazoni 2010-2024) libraries, respectively. During parsing, we identify and extract common document elements (e.g., title, headings, paragraphs, tables, lists, figures, and code) and reflect the correct hierarchy level if possible.

## 3.3 Pipelines

Pipelines in Docling serve as an orchestration layer which iterates through documents, gathers the extracted data from a parser backend, and applies a chain of models to: a) build up the DoclingDocument representation and b) enrich this representation further (e.g., classify images).

Docling provides two standard pipelines. The StandardPdfPipeline leverages several state-of-the-art AI models to reconstruct a high-quality DoclingDocument representation from PDF or image input, as described in section 4. The SimplePipeline handles all markup-based formats (Office, HTML, AsciiDoc) and may apply further enrichment models as well.

Pipelines can be fully customized by sub-classing from an abstract base class or cloning the default model pipeline. This effectively allows to fully customize the chain of models, add or replace models, and introduce additional pipeline configuration parameters. To create and use a custom model pipeline, you can provide a custom pipeline class as an argument to the main document conversion API.

## 4 PDF Conversion Pipeline

The capability to recover detailed structure and content from PDF and image files is one of Docling's defining features. In this section, we outline the underlying methods and models that drive the system.

Each document is first parsed by a PDF backend, which retrieves the programmatic text tokens, consisting of string content and its coordinates on the page, and also renders a bitmap image of each page to support downstream operations. Any image format input is wrapped in a PDF container