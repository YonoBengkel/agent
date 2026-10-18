import sys
import argparse
import opendataloader_pdf

def main():
    parser = argparse.ArgumentParser(description="PDF to Markdown Parser for Ingesting to Wiki")
    parser.add_argument("input", help="File PDF yang akan di-parse")
    parser.add_argument("--output", help="Folder output untuk Markdown", default=".")
    
    args = parser.parse_args()
    
    print(f"[*] Mengekstrak PDF: {args.input}")
    try:
        opendataloader_pdf.convert(
            input_path=args.input,
            output_dir=args.output,
            format="markdown"
        )
        print(f"[SUCCESS] Ekstraksi selesai. Hasil tersimpan di folder: {args.output}")
    except Exception as e:
        print(f"[ERROR] Gagal mengekstrak PDF: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
