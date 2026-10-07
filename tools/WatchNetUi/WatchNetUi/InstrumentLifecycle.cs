using System.IO;
using System.Text;
using System.Text.RegularExpressions;

namespace WatchNetUi;

/// <summary>
/// Add/remove instrument across barsSaver sec_list + bars/marks/net CSV (+ per-sec weights).
/// </summary>
public static class InstrumentLifecycle
{
    public static readonly int[] Intervals = [1, 10, 30, 240, 1440];
    public static readonly string[] ChartTfs = ["M1", "M10", "M30", "H4", "D1"];

    public static readonly string BarsSaverRoot = @"C:\QuikFinam\LuaScripts\barsSaver";
    public static readonly string SecListPath = Path.Combine(BarsSaverRoot, "sec_list.txt");

    private static readonly Regex EntryRe = new(
        @"\{\s*sec_code\s*=\s*""(?<sec>[^""]+)""\s*,\s*class_code\s*=\s*""(?<cls>[^""]+)""\s*,\s*interval\s*=\s*(?<iv>\d+)\s*\}",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    public sealed record Entry(string Sec, string ClassCode, int Interval);

    public sealed record ChangeReport(
        string Sec,
        string ClassCode,
        bool SecListChanged,
        int SecListRows,
        IReadOnlyList<string> DeletedFiles,
        string Note);

    /// <summary>File name stems charts/export may use for this sec (CNY/CR aliases).</summary>
    public static IReadOnlyList<string> FileSecNames(string sec, string classCode)
    {
        var names = new List<string> { sec };
        var u = sec.ToUpperInvariant();
        if (classCode.Equals("SPBFUT", StringComparison.OrdinalIgnoreCase))
        {
            if (u.StartsWith("CNY", StringComparison.Ordinal) || u is "CR" or "CRZ6")
            {
                foreach (var n in new[] { "CR", "CRZ6", "CNY12.26", "CNY-12.26" })
                    if (!names.Contains(n, StringComparer.OrdinalIgnoreCase))
                        names.Add(n);
            }
            else if (sec.Length > 2)
            {
                var root = sec[..^2];
                if (!names.Contains(root, StringComparer.OrdinalIgnoreCase))
                    names.Add(root);
            }
        }
        return names;
    }

    public static string NormalizeSecForBarsSaver(string sec, string classCode, out string? tip)
    {
        tip = null;
        var s = sec.Trim();
        var c = classCode.Trim().ToUpperInvariant();
        if (c == "SPBFUT" && s.StartsWith("CNY", StringComparison.OrdinalIgnoreCase))
        {
            tip = "В sec_list для CNY нужен код CreateDataSource (сейчас CRZ6), не CNY12.26 — подставляю CRZ6.";
            return "CRZ6";
        }
        if (c == "SPBFUT" && s.Equals("Si", StringComparison.OrdinalIgnoreCase))
        {
            tip = "Для Si в sec_list нужен SiZ6 — подставляю SiZ6.";
            return "SiZ6";
        }
        return s;
    }

    public static List<(string Sec, string ClassCode)> ListSecListInstruments(string? path = null)
    {
        return ReadEntries(path)
            .GroupBy(e => (e.Sec, e.ClassCode), StringPairComparer.Instance)
            .Select(g => g.Key)
            .OrderBy(k => k.Sec, StringComparer.OrdinalIgnoreCase)
            .ThenBy(k => k.ClassCode, StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    public static bool HasInstrument(string sec, string classCode, string? path = null)
    {
        var want = NormalizeKey(sec, classCode);
        return ReadEntries(path).Any(e => NormalizeKey(e.Sec, e.ClassCode) == want);
    }

    public static ChangeReport AddToSecList(string sec, string classCode, string? path = null)
    {
        path ??= SecListPath;
        var tip = (string?)null;
        sec = NormalizeSecForBarsSaver(sec, classCode, out tip);
        classCode = classCode.Trim().ToUpperInvariant();
        if (string.IsNullOrWhiteSpace(sec))
            throw new ArgumentException("пустой sec_code");

        var entries = ReadEntries(path);
        if (entries.Any(e => e.Sec.Equals(sec, StringComparison.OrdinalIgnoreCase)
                             && e.ClassCode.Equals(classCode, StringComparison.OrdinalIgnoreCase)))
        {
            return new ChangeReport(sec, classCode, false, 0, Array.Empty<string>(),
                tip ?? $"уже есть в sec_list: {sec}:{classCode}");
        }

        foreach (var iv in Intervals)
            entries.Add(new Entry(sec, classCode, iv));
        WriteEntries(path, entries);
        var note = "sec_list обновлён — перезапустите Lua barsSaver в QUIK, дождитесь CSV в data\\.";
        if (tip != null) note = tip + " " + note;
        return new ChangeReport(sec, classCode, true, Intervals.Length, Array.Empty<string>(), note);
    }

    public static ChangeReport RemoveEverywhere(
        string sec,
        string classCode,
        bool deleteBarsFiles = true,
        bool deleteMarksFiles = true,
        bool deleteNetFiles = true,
        string? secListPath = null)
    {
        secListPath ??= SecListPath;
        var tip = (string?)null;
        var listSec = NormalizeSecForBarsSaver(sec, classCode, out tip);
        classCode = classCode.Trim().ToUpperInvariant();

        var entries = ReadEntries(secListPath);
        var before = entries.Count;
        entries = entries
            .Where(e => !(e.Sec.Equals(listSec, StringComparison.OrdinalIgnoreCase)
                          && e.ClassCode.Equals(classCode, StringComparison.OrdinalIgnoreCase))
                     && !(e.Sec.Equals(sec, StringComparison.OrdinalIgnoreCase)
                          && e.ClassCode.Equals(classCode, StringComparison.OrdinalIgnoreCase)))
            .ToList();
        var removedRows = before - entries.Count;
        if (removedRows > 0)
            WriteEntries(secListPath, entries);

        var deleted = new List<string>();
        var names = FileSecNames(sec, classCode).Concat(FileSecNames(listSec, classCode)).Distinct(StringComparer.OrdinalIgnoreCase).ToList();

        if (deleteBarsFiles)
        {
            foreach (var name in names)
            foreach (var tf in ChartTfs)
            {
                TryDelete(Path.Combine(Paths.BarsDir, $"{name}_{classCode}_{tf}_.csv"), deleted);
            }
        }

        if (deleteMarksFiles)
        {
            foreach (var name in names)
            foreach (var tf in ChartTfs)
            {
                TryDelete(InstrumentScanner.MarksCsvPath(name, classCode, tf), deleted);
            }
        }

        if (deleteNetFiles)
        {
            foreach (var name in names)
            {
                foreach (var tf in ChartTfs)
                    TryDelete(InstrumentScanner.NetCsvPath(name, classCode, tf), deleted);
                TryDelete(Path.Combine(Paths.NetDir, $"net_{name}_{classCode}.npz"), deleted);
                TryDelete(Path.Combine(Paths.NetDir, $"net_{name}_{classCode}.npz.bak"), deleted);
            }
        }

        var note = removedRows > 0
            ? $"убрано из sec_list ({removedRows} строк); удалено файлов: {deleted.Count}. Перезапустите barsSaver."
            : $"в sec_list не было; удалено файлов: {deleted.Count}.";
        if (tip != null) note = tip + " " + note;
        return new ChangeReport(listSec, classCode, removedRows > 0, removedRows, deleted, note);
    }

    public static List<Entry> ReadEntries(string? path = null)
    {
        path ??= SecListPath;
        if (!File.Exists(path))
            return [];
        var text = File.ReadAllText(path, Encoding.UTF8);
        var list = new List<Entry>();
        foreach (Match m in EntryRe.Matches(text))
        {
            list.Add(new Entry(
                m.Groups["sec"].Value,
                m.Groups["cls"].Value,
                int.Parse(m.Groups["iv"].Value)));
        }
        return list;
    }

    public static void WriteEntries(string path, IReadOnlyList<Entry> entries)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        if (File.Exists(path))
        {
            var bak = path + ".bak";
            File.Copy(path, bak, overwrite: true);
        }

        var sb = new StringBuilder();
        sb.AppendLine("return {");
        sb.AppendLine();
        var i = 1;
        foreach (var e in entries)
        {
            sb.AppendLine(
                $"    [{i}] = {{ sec_code = \"{e.Sec}\", class_code = \"{e.ClassCode}\", interval = {e.Interval} }},");
            i++;
        }
        sb.AppendLine();
        sb.AppendLine("}");
        sb.AppendLine();
        File.WriteAllText(path, sb.ToString(), new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
    }

    private static void TryDelete(string path, List<string> deleted)
    {
        try
        {
            if (!File.Exists(path)) return;
            File.Delete(path);
            deleted.Add(path);
        }
        catch
        {
            // leave locked files; caller sees partial delete in log
        }
    }

    private static string NormalizeKey(string sec, string cls) =>
        $"{sec.Trim().ToUpperInvariant()}:{cls.Trim().ToUpperInvariant()}";

    private sealed class StringPairComparer : IEqualityComparer<(string Sec, string ClassCode)>
    {
        public static readonly StringPairComparer Instance = new();
        public bool Equals((string Sec, string ClassCode) x, (string Sec, string ClassCode) y) =>
            string.Equals(x.Sec, y.Sec, StringComparison.OrdinalIgnoreCase)
            && string.Equals(x.ClassCode, y.ClassCode, StringComparison.OrdinalIgnoreCase);
        public int GetHashCode((string Sec, string ClassCode) obj) =>
            HashCode.Combine(obj.Sec.ToUpperInvariant(), obj.ClassCode.ToUpperInvariant());
    }
}
