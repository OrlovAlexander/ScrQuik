using System.Globalization;
using System.IO;
using System.Text;

namespace WatchNetUi;

/// <summary>Reads CSV written by lua/SecDump.lua (QUIK getClassSecurities + getParamEx).</summary>
public static class QuikSecDump
{
    public static readonly string DefaultPath =
        Path.Combine(InstrumentLifecycle.BarsSaverRoot, "sec_dump.csv");

    private static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    public sealed record Row(
        string Sec,
        string ClassCode,
        string Name,
        string ShortName,
        double? PriceStep,
        double? Last,
        double? ValToday,
        double? VolToday,
        DateTime? MatDate,
        TimeSpan? MatTime);

    public sealed record Snapshot(
        string Path,
        DateTime? WriteTime,
        IReadOnlyList<Row> Rows,
        string Status);

    private static Snapshot? _cache;
    private static DateTime? _cacheMtime;
    private static IReadOnlyDictionary<string, Row>? _byKey;

    public static Snapshot LoadCached(string? path = null)
    {
        path ??= DefaultPath;
        DateTime? mtime = null;
        try
        {
            if (File.Exists(path)) mtime = File.GetLastWriteTime(path);
        }
        catch { /* ignore */ }

        if (_cache != null && Equals(_cacheMtime, mtime) && _byKey != null)
            return _cache;

        var snap = Load(path);
        _cache = snap;
        _cacheMtime = mtime;
        _byKey = snap.Rows.ToDictionary(
            r => Key(r.Sec, r.ClassCode),
            r => r,
            StringComparer.OrdinalIgnoreCase);
        return snap;
    }

    public static string Key(string sec, string classCode) => $"{sec}:{classCode}";

    public static Row? Find(string sec, string classCode)
    {
        LoadCached();
        if (_byKey != null && _byKey.TryGetValue(Key(sec, classCode), out var row))
            return row;
        return null;
    }

    public static string FormatVol(double? v)
    {
        if (v == null) return "—";
        var ru = CultureInfo.GetCultureInfo("ru-RU");
        var x = v.Value;
        if (Math.Abs(x) >= 1_000_000) return (x / 1_000_000).ToString("0.##", ru) + " млн";
        if (Math.Abs(x) >= 1_000) return (x / 1_000).ToString("0.#", ru) + " тыс";
        return x.ToString("N0", ru);
    }

    public static string FormatVal(double? v)
    {
        if (v == null) return "—";
        var ru = CultureInfo.GetCultureInfo("ru-RU");
        var x = v.Value;
        if (Math.Abs(x) >= 1_000_000_000) return (x / 1_000_000_000).ToString("0.##", ru) + " млрд";
        if (Math.Abs(x) >= 1_000_000) return (x / 1_000_000).ToString("0.##", ru) + " млн";
        if (Math.Abs(x) >= 1_000) return (x / 1_000).ToString("0.#", ru) + " тыс";
        return x.ToString("N0", ru);
    }

    public static string FormatLast(double? v)
    {
        if (v == null) return "—";
        var ru = CultureInfo.GetCultureInfo("ru-RU");
        var abs = Math.Abs(v.Value);
        if (abs >= 1000) return v.Value.ToString("N2", ru);
        if (abs >= 1) return v.Value.ToString("0.####", ru);
        return v.Value.ToString("0.######", ru);
    }

    public static Snapshot Load(string? path = null)
    {
        path ??= DefaultPath;
        if (!File.Exists(path))
        {
            return new Snapshot(path, null, Array.Empty<Row>(),
                $"нет файла {path} — запустите Lua SecDump в QUIK");
        }

        DateTime? mtime = null;
        try { mtime = File.GetLastWriteTime(path); } catch { /* ignore */ }

        var rows = new List<Row>();
        try
        {
            var bytes = File.ReadAllBytes(path);
            var text = DecodeDump(bytes);
            foreach (var line in text.Split(["\r\n", "\n"], StringSplitOptions.None))
            {
                var t = line.Trim();
                if (t.Length == 0) continue;
                if (t.StartsWith("sec_code", StringComparison.OrdinalIgnoreCase)) continue;
                var parts = SplitCsv(t);
                if (parts.Count < 2) continue;
                var sec = parts[0].Trim();
                var cls = parts[1].Trim();
                if (sec.Length == 0 || cls.Length == 0) continue;
                var name = parts.Count > 2 ? parts[2].Trim() : "";
                var shortName = parts.Count > 3 ? parts[3].Trim() : "";
                var priceStep = ParseDouble(parts, 4);
                var last = ParseDouble(parts, 5);
                var valToday = ParseDouble(parts, 6);
                var volToday = ParseDouble(parts, 7);
                var matDate = ParseDate(parts, 8);
                var matTime = ParseTime(parts, 9);
                rows.Add(new Row(sec, cls, name, shortName, priceStep, last, valToday, volToday, matDate, matTime));
            }
        }
        catch (Exception ex)
        {
            return new Snapshot(path, mtime, Array.Empty<Row>(), "ошибка чтения: " + ex.Message);
        }

        var age = mtime == null ? "" : $" · {BarsHealth.FormatAge(DateTime.Now - mtime.Value)} назад";
        var rich = rows.Count(r => r.ValToday != null || r.Last != null);
        var hint = rich > 0 ? $" · котировки {rich}" : " · без котировок — обновите SecDump.lua";
        return new Snapshot(path, mtime, rows, $"справочник QUIK: {rows.Count} строк{age}{hint}");
    }

    private static double? ParseDouble(List<string> parts, int i)
    {
        if (i >= parts.Count) return null;
        var s = parts[i].Trim().Replace(',', '.');
        if (s.Length == 0) return null;
        if (double.TryParse(s, NumberStyles.Float, Inv, out var v)) return v;
        return null;
    }

    private static DateTime? ParseDate(List<string> parts, int i)
    {
        if (i >= parts.Count) return null;
        var s = parts[i].Trim();
        if (s.Length == 0) return null;
        // 2026-12-15 or 15.12.2026 or 20261215
        if (DateTime.TryParse(s, Inv, DateTimeStyles.None, out var dt)) return dt.Date;
        if (DateTime.TryParse(s, CultureInfo.GetCultureInfo("ru-RU"), DateTimeStyles.None, out dt))
            return dt.Date;
        if (s.Length == 8 && long.TryParse(s, out var n))
        {
            var y = (int)(n / 10000);
            var m = (int)((n % 10000) / 100);
            var d = (int)(n % 100);
            try { return new DateTime(y, m, d); } catch { return null; }
        }
        return null;
    }

    private static TimeSpan? ParseTime(List<string> parts, int i)
    {
        if (i >= parts.Count) return null;
        var s = parts[i].Trim();
        if (s.Length == 0) return null;
        if (TimeSpan.TryParse(s, Inv, out var ts)) return ts;
        return null;
    }

    /// <summary>QUIK Lua writes ANSI (CP1251 on RU Windows); tolerate UTF-8 if present.</summary>
    private static string DecodeDump(byte[] bytes)
    {
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);

        if (bytes.Length >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF)
            return Encoding.UTF8.GetString(bytes, 3, bytes.Length - 3);

        try
        {
            return new UTF8Encoding(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true)
                .GetString(bytes);
        }
        catch (DecoderFallbackException)
        {
            return Encoding.GetEncoding(1251).GetString(bytes);
        }
    }

    public static IReadOnlyList<Row> Filter(
        IReadOnlyList<Row> rows,
        string? classCode,
        string? query,
        bool cryptoOnly = false)
    {
        IEnumerable<Row> q = rows;
        if (!string.IsNullOrWhiteSpace(classCode))
        {
            var c = classCode.Trim();
            q = q.Where(r => r.ClassCode.Equals(c, StringComparison.OrdinalIgnoreCase));
        }
        if (cryptoOnly)
            q = q.Where(IsCryptoLike);
        if (!string.IsNullOrWhiteSpace(query))
        {
            var p = query.Trim();
            q = q.Where(r =>
                r.Sec.Contains(p, StringComparison.OrdinalIgnoreCase)
                || r.Name.Contains(p, StringComparison.OrdinalIgnoreCase)
                || r.ShortName.Contains(p, StringComparison.OrdinalIgnoreCase));
        }
        // Default: liquid first (DataGrid can re-sort by column click).
        return q
            .OrderByDescending(r => r.ValToday ?? -1)
            .ThenBy(r => r.Sec, StringComparer.OrdinalIgnoreCase)
            .Take(2000)
            .ToList();
    }

    public static bool IsCryptoLike(Row r)
    {
        return ContainsAny(r.Sec, CryptoHints)
               || ContainsAny(r.Name, CryptoHints)
               || ContainsAny(r.ShortName, CryptoHints);
    }

    private static readonly string[] CryptoHints =
        ["BTC", "ETH", "USDT", "USDC", "SOL", "XRP", "BNB", "TON", "DOGE", "ADA", "CRYPTO"];

    private static bool ContainsAny(string text, string[] hints)
    {
        if (string.IsNullOrEmpty(text)) return false;
        foreach (var h in hints)
        {
            if (text.Contains(h, StringComparison.OrdinalIgnoreCase))
                return true;
        }
        return false;
    }

    private static List<string> SplitCsv(string line)
    {
        var parts = new List<string>();
        var cur = new StringBuilder();
        var inQuotes = false;
        for (var i = 0; i < line.Length; i++)
        {
            var ch = line[i];
            if (inQuotes)
            {
                if (ch == '"')
                {
                    if (i + 1 < line.Length && line[i + 1] == '"')
                    {
                        cur.Append('"');
                        i++;
                    }
                    else inQuotes = false;
                }
                else cur.Append(ch);
            }
            else if (ch == '"') inQuotes = true;
            else if (ch == ';')
            {
                parts.Add(cur.ToString());
                cur.Clear();
            }
            else cur.Append(ch);
        }
        parts.Add(cur.ToString());
        return parts;
    }
}
