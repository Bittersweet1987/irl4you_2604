/* IRL4YOU: pbflvfix - schreibt FLV-Videokacheln mit alter HEVC-Kennung (Codec-ID 12, so senden viele Handy-Apps) in das
 * "Enhanced RTMP"-Format um (ExVideoTagHeader mit FourCC hvc1), das GStreamers flvdemux versteht. Alles andere (H.264, Ton,
 * Metadaten) wird unverändert durchgereicht. Eigener Entwurf nach der veröffentlichten FLV- und Enhanced-RTMP-Spezifikation.
 *
 *   rtmpsrc ! pbflvfix ! flvdemux
 *
 * Alt:       Byte 0 = Bildtyp<<4 | 12, Byte 1 = Pakettyp (0 Konfiguration, 1 Bild, 2 Ende), Byte 2..4 = Zeitversatz, danach die Daten
 * Enhanced:  Byte 0 = 0x80 | Bildtyp<<4 | Pakettyp (0 Konfiguration, 1 Bild mit Zeitversatz, 2 Ende), 'hvc1', [Zeitversatz bei Pakettyp 1], Daten
 * Die Tag-Größe ändert sich nur bei Pakettyp 1 (+3 Byte); Größe im Tag-Kopf und "PreviousTagSize" werden neu geschrieben. */
#include <gst/gst.h>
#include <gst/base/gstadapter.h>
#include <string.h>

typedef struct {
  GstElement parent;
  GstPad *sinkpad, *srcpad;
  GstAdapter *adapter;
  gboolean header_done;
} PbFlvFix;

typedef struct {
  GstElementClass parent_class;
} PbFlvFixClass;

#define PB_TYPE_FLV_FIX (pb_flv_fix_get_type())
G_DEFINE_TYPE(PbFlvFix, pb_flv_fix, GST_TYPE_ELEMENT)

static GstStaticPadTemplate sink_tmpl = GST_STATIC_PAD_TEMPLATE("sink", GST_PAD_SINK, GST_PAD_ALWAYS, GST_STATIC_CAPS("video/x-flv"));
static GstStaticPadTemplate src_tmpl = GST_STATIC_PAD_TEMPLATE("src", GST_PAD_SRC, GST_PAD_ALWAYS, GST_STATIC_CAPS("video/x-flv"));

static void put24(guint8 *p, guint32 v) { p[0] = v >> 16; p[1] = v >> 8; p[2] = v; }
static void put32(guint8 *p, guint32 v) { p[0] = v >> 24; p[1] = v >> 16; p[2] = v >> 8; p[3] = v; }

/* Ein Tag (Kopf 11 Byte + Daten size + PreviousTagSize 4 Byte) umschreiben; Ergebnis an out anhängen */
static void convert_tag(const guint8 *tag, guint32 size, GByteArray *out)
{
  const guint8 *d = tag + 11;
  if (tag[0] == 9 && size >= 5 && (d[0] & 0x0f) == 12 && (d[0] >> 4) != 5 && d[1] <= 2) {
    guint ft = d[0] >> 4, pt = d[1];
    guint32 payload = size - 5, nsize = 1 + 4 + (pt == 1 ? 3 : 0) + (pt == 2 ? 0 : payload);
    guint8 hdr[11 + 5 + 3];
    memcpy(hdr, tag, 11);                       /* Typ, Zeitstempel und Stream-ID bleiben */
    put24(hdr + 1, nsize);
    guint n = 11;
    hdr[n++] = 0x80 | (ft << 4) | pt;
    memcpy(hdr + n, "hvc1", 4); n += 4;
    if (pt == 1) { memcpy(hdr + n, d + 2, 3); n += 3; }
    g_byte_array_append(out, hdr, n);
    if (pt != 2)
      g_byte_array_append(out, d + 5, payload);
    guint8 prev[4];
    put32(prev, 11 + nsize);
    g_byte_array_append(out, prev, 4);
    return;
  }
  g_byte_array_append(out, tag, 11 + size + 4);
}

static GstFlowReturn chain(GstPad *pad, GstObject *parent, GstBuffer *buf)
{
  PbFlvFix *self = (PbFlvFix *)parent;
  (void)pad;
  gst_adapter_push(self->adapter, buf);
  GByteArray *out = g_byte_array_new();
  for (;;) {
    gsize avail = gst_adapter_available(self->adapter);
    if (!self->header_done) {
      if (avail < 13)
        break;
      const guint8 *h = gst_adapter_map(self->adapter, 13);
      g_byte_array_append(out, h, 13);
      gst_adapter_unmap(self->adapter);
      gst_adapter_flush(self->adapter, 13);
      self->header_done = TRUE;
      continue;
    }
    if (avail < 11)
      break;
    const guint8 *h = gst_adapter_map(self->adapter, 11);
    guint32 size = (h[1] << 16) | (h[2] << 8) | h[3];
    gst_adapter_unmap(self->adapter);
    gsize total = 11 + (gsize)size + 4;
    if (avail < total)
      break;
    const guint8 *tag = gst_adapter_map(self->adapter, total);
    convert_tag(tag, size, out);
    gst_adapter_unmap(self->adapter);
    gst_adapter_flush(self->adapter, total);
  }
  if (out->len == 0) {
    g_byte_array_free(out, TRUE);
    return GST_FLOW_OK;
  }
  gsize len = out->len;
  GstBuffer *ob = gst_buffer_new_wrapped(g_byte_array_free(out, FALSE), len);
  return gst_pad_push(self->srcpad, ob);
}

static gboolean sink_event(GstPad *pad, GstObject *parent, GstEvent *ev)
{
  PbFlvFix *self = (PbFlvFix *)parent;
  if (GST_EVENT_TYPE(ev) == GST_EVENT_FLUSH_STOP || GST_EVENT_TYPE(ev) == GST_EVENT_SEGMENT) {
    if (GST_EVENT_TYPE(ev) == GST_EVENT_FLUSH_STOP) {
      gst_adapter_clear(self->adapter);
      self->header_done = FALSE;
    }
  }
  return gst_pad_event_default(pad, parent, ev);
}

static void finalize(GObject *o)
{
  PbFlvFix *self = (PbFlvFix *)o;
  g_object_unref(self->adapter);
  G_OBJECT_CLASS(pb_flv_fix_parent_class)->finalize(o);
}

static void pb_flv_fix_class_init(PbFlvFixClass *klass)
{
  GstElementClass *ec = GST_ELEMENT_CLASS(klass);
  G_OBJECT_CLASS(klass)->finalize = finalize;
  gst_element_class_add_static_pad_template(ec, &sink_tmpl);
  gst_element_class_add_static_pad_template(ec, &src_tmpl);
  gst_element_class_set_static_metadata(ec, "IRL4YOU FLV-HEVC-Umschreiber", "Filter/Converter",
                                        "Alte HEVC-Kennung (Codec-ID 12) in Enhanced-FLV (hvc1) umschreiben", "IRL4YOU");
}

static void pb_flv_fix_init(PbFlvFix *self)
{
  self->sinkpad = gst_pad_new_from_static_template(&sink_tmpl, "sink");
  self->srcpad = gst_pad_new_from_static_template(&src_tmpl, "src");
  gst_pad_set_chain_function(self->sinkpad, chain);
  gst_pad_set_event_function(self->sinkpad, sink_event);
  gst_element_add_pad(GST_ELEMENT(self), self->sinkpad);
  gst_element_add_pad(GST_ELEMENT(self), self->srcpad);
  self->adapter = gst_adapter_new();
  self->header_done = FALSE;
}

gboolean pb_flv_fix_register(GstPlugin *plugin)
{
  return gst_element_register(plugin, "pbflvfix", GST_RANK_NONE, PB_TYPE_FLV_FIX);
}
