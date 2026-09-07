# Interaction and accessible static delivery

Plan a complete linear reading path even when the live talk includes links,
reveals, video, or audience exercises. A recipient opening the PDF should be able
to recover the claim, evidence, sequence, and limitation without attending the
talk or executing an interaction.

## Use interaction for a named task

For discussion links, give the destination a meaningful label and retain stable
slide identifiers or appendix references. Provide a return route for the speaker.
The main sequence must still reach every necessary conclusion if a link fails.
For a teaching prompt, keep the question and enough context visible before showing
the answer; include the answer or an explicit solution reference in the handout.

Decide whether a link is needed for the evidence itself or merely offers detail.
If the central result exists only behind a link, place a source-faithful summary
in the deck. Test links in the actual requested output. A working PPTX link does
not prove that the PDF exporter preserved it.

## Give motion a static equivalent

| Live behavior | Static representation | Review question |
|---|---|---|
| Reveal a method stage | Numbered stages with explicit arrows and labels | Can the process be followed without remembering an earlier frame? |
| Switch between conditions | Side-by-side states or consecutive labeled pages | Are sample, scale, and changed variable still identifiable? |
| Animate a trajectory | Selected labeled states plus a path or summary chart | Are state selection and time scale stated? |
| Play explanatory media | Representative frames, captions, and a textual account | Is the scientifically relevant observation preserved? |
| Reveal an exercise answer | Separate prompt and solution regions or pages | Can the learner attempt the task before encountering the solution? |
| Open backup evidence | Visible appendix reference and linear appendix pages | Can the evidence be reached after static export? |

Prefer no motion when motion adds no explanatory information. For a live sequence,
avoid flashing and repeated decorative movement; permit a reduced-motion version
using immediate state changes. Preserve labels and comparison anchors between
states. These are local delivery choices, not a claim that animation or timing
has been tested against an accessibility standard.

The recommender may assign `appear` to method roles and `fade` to state comparison.
That assignment is a suggestion. Its `static_fallback` and `reduced_motion` flags
record intended behavior; they do not generate or inspect a fallback artifact.
The author must build and inspect the chosen representation.

## Make the document navigable beyond its visual appearance

Microsoft's PowerPoint accessibility guidance recommends meaningful slide titles,
alternative text, logical reading order, descriptive links, and an accessibility
check. Its PDF guidance calls for accessibility tags. The available controls vary
by platform and version; inspect the actual editor and export result. See
[Microsoft's PowerPoint accessibility guide](https://support.microsoft.com/en-us/accessibility/powerpoint/make-your-powerpoint-presentations-accessible-to-people-with-disabilities).

Apply those checks to the research content deliberately. A diagram description
should identify the important entities, direction, and outcome. A chart description
should describe the comparison and its limitation, with access to the numeric
evidence when needed. Review generated alternative text for factual errors. Mark
decoration appropriately so it does not interrupt reading of evidence.

Check object order by following the intended account: title, evidence, explanation,
qualification, source. Place the object-level reading order in the presentation
tool; a list in a planning JSON file is only an instruction. Speaker notes may
supplement descriptions, but notes alone are not proof of equivalent access in a
PDF that does not contain them. Include essential descriptions in the distributed
artifact or a clearly identified companion document.

Use simple table structures with explicit row and column meanings. Explain dense
equations and abbreviations in accessible text. Provide captions for spoken media
and a text account of scientifically meaningful sound or action. Identify a link
by what it opens, not only by its color or position.

## Adapt the canvas and language

Treat 16:9, 4:3, a handout, a thumbnail, and projection as different viewing
conditions. Recompose evidence regions when the aspect ratio changes. Keep image
proportions and comparable scales intact. For a bilingual handout, consider
paired pages when duplicated text would crowd the visual. Preserve the same slide
IDs and source traces between variants so discussion and citations stay usable.

Font substitution, text overflow, equation rendering, raster resolution, and PDF
reading order can change during export. Inspect the requested format after export
rather than inferring its behavior from the editor preview. A PDF consisting only
of page images may look correct while losing selectable text and structural access.

## Record exactly what was checked

Use a short format-specific record: artifact and version, renderer/editor,
inspected views, issue, correction, and remaining manual check. Check full slides
for clipping and reading size; check a deck overview for consistency; check static
pages for missing reveal states; inspect exported text, links, descriptions, and
tags with available tools. Reopen the distributed file when possible.

Report inaccessible or unverified features explicitly, for example “PDF visuals
inspected; tag order not checked.” A passing plan validator proves neither a
rendered artifact nor a complete accessibility assessment. An actual screen-reader
or venue projection check is a separate check and should be reported only if run.
