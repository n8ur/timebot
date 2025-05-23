# timebot.febo.com 

This is **timebot**, a RAG-assisted expert system created
for time and frequency applications, but the code should be
usable for other knowledgebases with only minor changes.

## Description

**timebot** consists of several Python programs that ingest (a) Mailman v2 mailing
list archive files in HTML format; (b) PDF files; and (c) web sites into two databases:
chromadb for similarity searches, and whoosh for full-text indexing.

A RAG server allows queries into these databases.

A chat server (built using the streamlit framework) accepts user queries, retrieves
relevant documents from the databases, and forwards the query and context to an external
LLM.

## Authors

John Ackermann N8UR  -- jra at febo dot com

## Version History
* 0.1
    * Initial Release

## License

This project is licensed under the MIT License - see the LICENSE.md file for details.
Most of this code was generated by LLMs, so I don't claim much credit for it, though
I suppose I have to accept the blame...
