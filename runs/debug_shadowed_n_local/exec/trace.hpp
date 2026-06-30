#ifndef CP_TRACE_TRACE_HPP
#define CP_TRACE_TRACE_HPP

#include <cstddef>
#include <cstdint>
#include <fstream>
#include <istream>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>

namespace cp_trace {

struct ArrayRegistration {
    std::string name;
    std::size_t size;
    std::string structure;
    int index_base;
};

inline std::string json_escape(const std::string& value) {
    std::ostringstream out;
    for (char ch : value) {
        switch (ch) {
            case '\\': out << "\\\\"; break;
            case '"': out << "\\\""; break;
            case '\n': out << "\\n"; break;
            case '\r': out << "\\r"; break;
            case '\t': out << "\\t"; break;
            default: out << ch; break;
        }
    }
    return out.str();
}

template <typename T>
class is_streamable {
    template <typename U>
    static auto test(int) -> decltype(std::declval<std::ostringstream&>() << std::declval<const U&>(), std::true_type());

    template <typename>
    static std::false_type test(...);

public:
    static constexpr bool value = decltype(test<T>(0))::value;
};

template <typename T>
inline typename std::enable_if<is_streamable<T>::value, std::string>::type to_string_value(const T& value) {
    std::ostringstream out;
    out << value;
    return out.str();
}

template <typename T>
inline typename std::enable_if<!is_streamable<T>::value, std::string>::type to_string_value(const T& value) {
    (void)value;
    return "<object>";
}

class TraceWriter {
public:
    static TraceWriter& instance() {
        static TraceWriter writer;
        return writer;
    }

    void open(const std::string& path) {
        if (out_.is_open()) {
            return;
        }
        out_.clear();
        out_.open(path.c_str(), std::ios::out | std::ios::trunc);
        if (!out_.is_open()) {
            throw std::runtime_error("Cannot open trace file: " + path);
        }
        for (std::size_t i = 0; i < pending_arrays_.size(); ++i) {
            write_array(pending_arrays_[i]);
        }
        pending_arrays_.clear();
    }

    void close() {
        if (out_.is_open()) {
            out_.flush();
            out_.close();
        }
    }

    void register_array(const std::string& name, std::size_t size,
                        const std::string& structure = "",
                        int index_base = 0) {
        ArrayRegistration registration = {name, size, structure, index_base};
        if (!out_.is_open()) {
            pending_arrays_.push_back(registration);
            return;
        }
        write_array(registration);
    }

    std::uint64_t begin_operation(const std::string& kind,
                                  const std::string& array,
                                  int n,
                                  const char* file,
                                  int line) {
        ensure_open();
        const std::uint64_t op_id = ++last_op_id_;
        const std::uint64_t parent_op_id = current_operation();
        op_stack_.push_back(OperationFrame{op_id, array});
        out_ << "{\"event\":\"op_begin\",\"seq\":" << next_seq()
             << ",\"op_id\":" << op_id
             << ",\"parent_op_id\":" << parent_op_id
             << ",\"kind\":\"" << json_escape(kind) << "\""
             << ",\"array\":\"" << json_escape(array) << "\""
             << ",\"n\":" << n
             << ",\"file\":\"" << json_escape(file ? file : "") << "\""
             << ",\"line\":" << line
             << "}\n";
        return op_id;
    }

    void end_operation() {
        ensure_open();
        const std::uint64_t op_id = current_operation();
        out_ << "{\"event\":\"op_end\",\"seq\":" << next_seq()
             << ",\"op_id\":" << op_id << "}\n";
        if (!op_stack_.empty()) {
            op_stack_.pop_back();
        }
    }

    template <typename T>
    void param(const std::string& key, const T& value) {
        ensure_open();
        out_ << "{\"event\":\"op_param\",\"seq\":" << next_seq()
             << ",\"op_id\":" << current_operation()
             << ",\"key\":\"" << json_escape(key) << "\""
             << ",\"value\":\"" << json_escape(to_string_value(value)) << "\""
             << "}\n";
    }

    template <typename T>
    void access(const std::string& mode,
                const std::string& array,
                std::size_t index,
                const T& value,
                const char* file,
                int line) {
        ensure_open();
        out_ << "{\"event\":\"access\",\"seq\":" << next_seq()
             << ",\"op_id\":" << current_operation_for_array(array)
             << ",\"mode\":\"" << json_escape(mode) << "\""
             << ",\"array\":\"" << json_escape(array) << "\""
             << ",\"index\":" << index
             << ",\"value\":\"" << json_escape(to_string_value(value)) << "\""
             << ",\"file\":\"" << json_escape(file ? file : "") << "\""
             << ",\"line\":" << line
             << "}\n";
    }

    template <typename T>
    void watch(const std::string& name,
               const T& value,
               const char* file,
               int line) {
        ensure_open();
        out_ << "{\"event\":\"watch\",\"seq\":" << next_seq()
             << ",\"op_id\":" << current_operation()
             << ",\"name\":\"" << json_escape(name) << "\""
             << ",\"value\":\"" << json_escape(to_string_value(value)) << "\""
             << ",\"file\":\"" << json_escape(file ? file : "") << "\""
             << ",\"line\":" << line
             << "}\n";
    }

    void source_line(int line, const std::string& kind) {
        ensure_open();
        out_ << "{\"event\":\"line\",\"seq\":" << next_seq()
             << ",\"op_id\":" << current_operation()
             << ",\"kind\":\"" << json_escape(kind) << "\""
             << ",\"file\":\"source.cpp\""
             << ",\"line\":" << line
             << "}\n";
    }

    template <typename T>
    bool condition(int line, const T& value) {
        const bool result = static_cast<bool>(value);
        ensure_open();
        out_ << "{\"event\":\"line\",\"seq\":" << next_seq()
             << ",\"op_id\":" << current_operation()
             << ",\"kind\":\"condition\""
             << ",\"value\":\"" << (result ? "true" : "false") << "\""
             << ",\"file\":\"source.cpp\""
             << ",\"line\":" << line
             << "}\n";
        return result;
    }

private:
    TraceWriter() = default;

    void ensure_open() {
        if (!out_.is_open()) {
            open("trace.jsonl");
        }
    }

    std::uint64_t next_seq() {
        return ++seq_;
    }

    std::uint64_t current_operation() const {
        if (op_stack_.empty()) {
            return 0;
        }
        return op_stack_.back().op_id;
    }

    std::uint64_t current_operation_for_array(const std::string& array) const {
        for (std::vector<OperationFrame>::const_reverse_iterator it = op_stack_.rbegin(); it != op_stack_.rend(); ++it) {
            if (it->array == array) {
                return it->op_id;
            }
        }
        return current_operation();
    }

    void write_array(const ArrayRegistration& registration) {
        out_ << "{\"event\":\"array\",\"seq\":" << next_seq()
             << ",\"array\":\"" << json_escape(registration.name) << "\""
             << ",\"size\":" << registration.size
             << ",\"structure\":\"" << json_escape(registration.structure) << "\""
             << ",\"index_base\":" << registration.index_base
             << "}\n";
    }

    std::ofstream out_;
    std::uint64_t seq_ = 0;
    std::uint64_t last_op_id_ = 0;
    struct OperationFrame {
        std::uint64_t op_id;
        std::string array;
    };
    std::vector<OperationFrame> op_stack_;
    std::vector<ArrayRegistration> pending_arrays_;
};

class OperationScope {
public:
    OperationScope(const std::string& kind,
                   const std::string& array,
                   int n,
                   const char* file,
                   int line)
        : active_(true) {
        TraceWriter::instance().begin_operation(kind, array, n, file, line);
    }

    ~OperationScope() {
        if (active_) {
            TraceWriter::instance().end_operation();
        }
    }

    OperationScope(const OperationScope&) = delete;
    OperationScope& operator=(const OperationScope&) = delete;

private:
    bool active_;
};

template <typename T>
class TrackedArray {
public:
    class Ref {
    public:
        Ref(TrackedArray& owner, std::size_t index, const char* file, int line)
            : owner_(owner), index_(index), file_(file), line_(line) {}

        operator T() const {
            owner_.check_index(index_);
            const T value = owner_.data_[index_];
            TraceWriter::instance().access("read", owner_.name_, index_, value, file_, line_);
            return value;
        }

        Ref& operator=(const T& value) {
            owner_.check_index(index_);
            owner_.data_[index_] = value;
            TraceWriter::instance().access("write", owner_.name_, index_, value, file_, line_);
            return *this;
        }

        Ref& operator=(const Ref& other) {
            return *this = static_cast<T>(other);
        }

        Ref& operator+=(const T& delta) {
            const T next = static_cast<T>(*this) + delta;
            *this = next;
            return *this;
        }

        Ref& operator-=(const T& delta) {
            const T next = static_cast<T>(*this) - delta;
            *this = next;
            return *this;
        }

        friend std::istream& operator>>(std::istream& in, Ref ref) {
            T value;
            in >> value;
            ref = value;
            return in;
        }

    private:
        TrackedArray& owner_;
        std::size_t index_;
        const char* file_;
        int line_;
    };

    template <typename Field>
    class FieldRef {
    public:
        FieldRef(TrackedArray& owner, std::size_t index, const char* field_name, Field T::* member, const char* file, int line)
            : owner_(owner), index_(index), field_name_(field_name ? field_name : ""), member_(member), file_(file), line_(line) {}

        operator Field() const {
            owner_.check_index(index_);
            const Field value = owner_.data_[index_].*member_;
            TraceWriter::instance().access("read", owner_.name_ + "." + field_name_, index_, value, file_, line_);
            return value;
        }

        FieldRef& operator=(const Field& value) {
            owner_.check_index(index_);
            owner_.data_[index_].*member_ = value;
            TraceWriter::instance().access("write", owner_.name_ + "." + field_name_, index_, value, file_, line_);
            return *this;
        }

        FieldRef& operator=(const FieldRef& other) {
            return *this = static_cast<Field>(other);
        }

        FieldRef& operator+=(const Field& delta) {
            const Field next = static_cast<Field>(*this) + delta;
            *this = next;
            return *this;
        }

        FieldRef& operator-=(const Field& delta) {
            const Field next = static_cast<Field>(*this) - delta;
            *this = next;
            return *this;
        }

    private:
        TrackedArray& owner_;
        std::size_t index_;
        std::string field_name_;
        Field T::* member_;
        const char* file_;
        int line_;
    };

    TrackedArray(const std::string& name,
                 std::size_t size,
                 const T& initial = T(),
                 const std::string& structure = "",
                 int index_base = 0)
        : name_(name), structure_(structure), index_base_(index_base), data_(size, initial) {
        TraceWriter::instance().register_array(name_, size, structure_, index_base_);
    }

    void resize(std::size_t size) {
        data_.resize(size);
        TraceWriter::instance().register_array(name_, size, structure_, index_base_);
    }

    void resize(std::size_t size, const T& value) {
        data_.resize(size, value);
        TraceWriter::instance().register_array(name_, size, structure_, index_base_);
    }

    Ref at(std::size_t index, const char* file, int line) {
        return Ref(*this, index, file, line);
    }

    template <typename Field, typename U = T, typename = std::enable_if_t<std::is_class<U>::value>>
    FieldRef<Field> field_at(std::size_t index, const char* field_name, Field U::* member, const char* file, int line) {
        return FieldRef<Field>(*this, index, field_name, member, file, line);
    }

    Ref operator[](std::size_t index) {
        return at(index, "", 0);
    }

    const T& raw(std::size_t index) const {
        check_index(index);
        return data_[index];
    }

    std::size_t size() const {
        return data_.size();
    }

private:
    void check_index(std::size_t index) const {
        if (index >= data_.size()) {
            throw std::out_of_range("TrackedArray index out of range: " + name_);
        }
    }

    std::string name_;
    std::string structure_;
    int index_base_;
    std::vector<T> data_;
};

}  // namespace cp_trace

#define CP_TRACE_OPEN(path) ::cp_trace::TraceWriter::instance().open(path)
#define CP_TRACE_CLOSE() ::cp_trace::TraceWriter::instance().close()
#define CP_TRACE_CONCAT_INNER(left, right) left##right
#define CP_TRACE_CONCAT(left, right) CP_TRACE_CONCAT_INNER(left, right)
#define CP_TRACE_SCOPE(kind, array_name, logical_n) \
    ::cp_trace::OperationScope CP_TRACE_CONCAT(cp_trace_scope_, __LINE__)((kind), (array_name), (logical_n), __FILE__, __LINE__)
#define CP_TRACE_PARAM(key, value) ::cp_trace::TraceWriter::instance().param((key), (value))
#define CP_TRACE_AT(array_obj, index_expr) (array_obj).at((index_expr), __FILE__, __LINE__)
#define CP_TRACE_FIELD_AT(array_obj, index_expr, field_name) \
    (array_obj).field_at((index_expr), #field_name, &std::remove_cv_t<std::remove_reference_t<decltype((array_obj).raw(0))>>::field_name, __FILE__, __LINE__)
#define CP_TRACE_WATCH(name, value) ::cp_trace::TraceWriter::instance().watch((name), (value), __FILE__, __LINE__)
#define CP_TRACE_LINE(line_no, kind) ::cp_trace::TraceWriter::instance().source_line((line_no), (kind))
#define CP_TRACE_COND(line_no, expr) ::cp_trace::TraceWriter::instance().condition((line_no), (expr))

#endif  // CP_TRACE_TRACE_HPP
